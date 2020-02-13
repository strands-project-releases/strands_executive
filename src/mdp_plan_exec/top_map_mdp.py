import yaml
from copy import deepcopy
from mdp import Mdp, MdpTransitionDef, MdpPropDef
import rospy
import actionlib
from actionlib_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from strands_navigation_msgs.srv import PredictEdgeState
from strands_navigation_msgs.msg import TopologicalMap
from door_pass.srv import PredictDoorState
from strands_executive_msgs.msg import MdpAction, MdpActionOutcome, StringIntPair, StringTriple
import strands_executive_msgs.mdp_action_utils as mau 
from mongodb_store.message_store import MessageStoreProxy
from mongodb_store_msgs.msg import StringPair


class TopMapMdp(Mdp):
    def __init__(self, explicit_doors=False, forget_doors=False, model_fatal_fails=False):
        Mdp.__init__(self)       
        got_service=False
        while not got_service:
            try:
                rospy.wait_for_service("/topological_prediction/predict_edges", 1)
                got_service=True
            except rospy.ROSException,e:
                rospy.loginfo("Waiting for predict_edges service...")
            if rospy.is_shutdown():
                return
        self.mongo=MessageStoreProxy()
        
        self.explicit_doors=explicit_doors
        self.forget_doors = forget_doors
        self.model_fatal_fails=model_fatal_fails
        
        self.new_top_map = False
        rospy.Subscriber("/topological_map", TopologicalMap, self.top_map_sub)
        while not self.new_top_map:
            rospy.loginfo("Waiting for topological map...")
            rospy.sleep(1)
        self.get_edge_estimates=rospy.ServiceProxy("/topological_prediction/predict_edges", PredictEdgeState)        
        
        self.nav_actions=[]
        self.door_pass_actions=rospy.get_param("/door_pass_actions", ["door_wait_and_pass", "door_wait_and_move_base"])
        door_wait_params_file = rospy.get_param("/door_wait_params_file", None)
        self.door_wait_params = {'types': ["int", "int", "float"], 'default':[15, 2, 60]} #[n_closed_door, consecutive_open_secs, wait_timeout] - timeout is a float and needs to be the last element of the msg type. TODO make all this less hacky.
        self.door_timeouts={}
        if door_wait_params_file is not None and explicit_doors:
            self.read_door_wait_params(door_wait_params_file)
        
        self.door_transitions=[]
        self.door_transitions_edge_ids = []
        self.door_timeouts={}
        self.action_descriptions={}
        self.create_top_map_mdp_structure()
        
        #save nav mdp structure for reset
        self.nav_template={'n_state_vars':self.n_state_vars,
                            'state_vars':deepcopy(self.state_vars),
                            'initial_state':deepcopy(self.initial_state),
                            'action_descriptions':deepcopy(self.action_descriptions),
                            'transitions':deepcopy(self.transitions)}
        
        self.last_prediction_epoch = None
        self.get_new_preds_threshold = rospy.Duration(60*5)
        
        rospy.loginfo("Topological MDP initialised")


    def reset_structure(self):
        self.n_state_vars = self.nav_template['n_state_vars']
        self.state_vars = deepcopy(self.nav_template['state_vars'])
        self.initial_state = deepcopy(self.nav_template['initial_state'])
        self.action_descriptions = deepcopy(self.nav_template['action_descriptions'])
        self.transitions = deepcopy(self.nav_template['transitions'])



    def read_door_wait_params(self, file_name):
        try:
            stream = open(file_name, 'r')
            yaml_config=yaml.load(stream)
        except Exception, e:
            rospy.logwarn("Error loading yaml config for door waits: " + str(e) + ". Using default values for all doors.")
            return
        self.door_wait_params.update(yaml_config)
        print self.door_wait_params

    def check_spaces_in_top_map(self):
        for node in self.top_map.nodes:
            if ' ' in node.name:
                raise SyntaxError("The topological node name '" + node.name + "' has a white space. Remove it")
            for edge in node.edges:
                if ' ' in edge.edge_id:
                    raise SyntaxError("An edge from '" + node.name + "' has an edge_id '" + edge.edge_id + "' with a white space. Remove it")

    def top_map_sub(self, msg):
        self.new_top_map = True
        self.top_map = msg
        self.check_spaces_in_top_map()
        

    def create_top_map_mdp_structure(self):
        if self.new_top_map:
            rospy.loginfo("Updating topological map")
            self.new_top_map=False
            self.n_state_vars=1
            self.state_vars=['waypoint']
            self.initial_state={'waypoint':0}
            n_waypoints=len(self.top_map.nodes)
            if self.model_fatal_fails:
                self.state_vars_range={'waypoint':(-1,n_waypoints-1)}
            else:
                self.state_vars_range={'waypoint':(0,n_waypoints-1)}
                    
            self.n_props=n_waypoints
            self.props=[]
            self.props_def = {}
            
            self.reward_names=['time']
            
            i=0
            for node in self.top_map.nodes:
                waypoint_name=node.name
                self.props.append(waypoint_name)            
                self.props_def[waypoint_name]=MdpPropDef(name=waypoint_name,
                                                        conds={'waypoint':i})
                i=i+1
            
            i = 0
            self.n_actions = 0
            self.actions = []
            self.nav_actions = []
            self.transitions = []
            self.door_transitions = []
            self.door_transitions_edge_ids = []
            for node in self.top_map.nodes:
                source_name=node.name
                for edge in node.edges:
                    target_index=self.props.index(edge.node)
                    action_name=edge.edge_id
                    self.actions.append(action_name)
                    self.nav_actions.append(action_name)
                    trans=MdpTransitionDef(action_name=action_name,
                                                    pre_conds={'waypoint':i},
                                                    prob_post_conds=[(1.0, {'waypoint':target_index})],
                                                    rewards={'time':1.0})
                    self.transitions.append(trans)
                    if edge.action in self.door_pass_actions:
                        self.door_transitions.append(trans)
                        self.door_transitions_edge_ids.append(edge.edge_id)
                        if self.door_wait_params.has_key(edge.edge_id):
                            self.door_timeouts[edge.edge_id] = self.door_wait_params[edge.edge_id][-1] #assumes timeout is the lass param of the action TODO be less hacky
                        else:
                            self.door_timeouts[edge.edge_id] = self.door_wait_params['default'][-1]
                    self.n_actions=self.n_actions+1 # all actions have a different name
                i=i+1
            
            #DOOR MODELLING
            if self.explicit_doors:  
                self.n_door_edges=0
                self.edge_to_door_dict={}
                self.add_door_model(self.forget_doors)
                self.get_door_estimates=rospy.ServiceProxy("/door_prediction/predict_doors", PredictDoorState)
        else:
            self.reset_structure()
                    
            

    def parse_sta_to_waypoints(self, sta_file, n_states):
        state_vector_names=[None]*n_states
        sta=open(sta_file)
        sta.readline()
        for line in sta:
            line=line.split(':')
            state_vector_names[int(line[0])]=self.get_waypoint_prop(int(line[1][1:-2]))
        return state_vector_names
    
    def map_state_vectors_to_waypoint_expectations(self, sta_file, exp_time_state_vector, prob_state_vector=None, exp_prog_state_vector=None):
        waypoint_names=[]
        waypoint_probs=[]
        waypoint_progs=[]
        waypoint_times=[]
        f=open(sta_file)  
        variables = f.readline()
        variables = variables.split(',')
        variables[0] = variables[0].strip('(')
        variables[-1] = variables[-1].strip(')\n')
       
        for line in f:
            states_string = line.split(':')
            state_id=int(states_string[0])
            state_list = states_string[1].split(',')
            state_list[0] = state_list[0].strip('(')
            state_list[-1] = state_list[-1].strip(')\n')
            state_dict={}
            waypoint_name=None
            for (var_name, value) in zip(variables, state_list):
                if var_name=="waypoint":
                    waypoint_name=self.get_waypoint_prop(int(value))
                else:
                    state_dict[var_name] = int(value)
            if self.check_cond_sat(state_dict, self.initial_state):
                waypoint_names.append(waypoint_name)
                waypoint_probs.append(1)
                waypoint_progs.append(1)
                waypoint_times.append(exp_time_state_vector[state_id])
        f.close()
        return (waypoint_names, waypoint_probs, waypoint_progs, waypoint_times)
  
    
    def get_waypoint_prop(self, waypoint_var_val):
        for key, value  in self.props_def.iteritems():
            if value.conds['waypoint']==waypoint_var_val:
                return key
        rospy.logerr("Waypoint not found!")
        
    def get_waypoint_var_val(self, waypoint_prop):
        if self.props_def.has_key(waypoint_prop):
            return self.props_def[waypoint_prop].conds['waypoint']
        else:
            return None

    def get_waypoint_pose_argument(self, waypoint):
        for node in self.top_map.nodes:
            if node.name==waypoint:
                return self.mongo.insert(PoseStamped(pose=node.pose))
              
    def set_initial_state_from_waypoint(self,current_waypoint):
        self.initial_state['waypoint']=self.props_def[current_waypoint].conds['waypoint']
        
    def target_in_topological_map(self, waypoint):
        return waypoint in [node.name for node in self.top_map.nodes]
    
    def add_door_check_action_description(self, source_wp, target_wp, action_name, door_state_var_name, edge_id):        
        action_description=MdpAction()
        action_description.name=action_name
        action_description.action_server="door_wait"
        action_description.waypoints=[source_wp]
        action_description.pre_conds=[StringIntPair(string_data=door_state_var_name, int_data=-1)]
        pose_id=self.get_waypoint_pose_argument(target_wp)
        mau.add_object_id_argument(action_description, pose_id, PoseStamped)
        if self.door_wait_params.has_key(edge_id):
            extra_params = self.door_wait_params[edge_id]
        else:
            extra_params = self.door_wait_params["default"]
        for (param, type) in zip(extra_params, self.door_wait_params['types']):
            if type == 'int':
                mau.add_int_argument(action_description, param)
            elif type == 'float':
                mau.add_float_argument(action_description, param)
            else:
                rospy.logerr("Need to implement adding of argument of type " + type + ".")
                
        
        outcome=MdpActionOutcome()
        outcome.probability=0.9
        outcome.post_conds=[StringIntPair(string_data=door_state_var_name, int_data=1)]
        outcome.duration_probs=[1]
        outcome.durations=[float(self.door_timeouts[edge_id])/2]
        outcome.status=[GoalStatus.SUCCEEDED]
        outcome.result=[StringTriple(attribute="open", type=MdpActionOutcome.BOOL_TYPE, value="True")]
        action_description.outcomes.append(outcome)
        outcome=MdpActionOutcome()
        outcome.probability=0.1
        outcome.post_conds=[StringIntPair(string_data=door_state_var_name, int_data=0)]
        outcome.duration_probs=[1]
        outcome.durations=[self.door_timeouts[edge_id]]
        outcome.status=[GoalStatus.SUCCEEDED]
        outcome.result=[StringTriple(attribute="open", type=MdpActionOutcome.BOOL_TYPE, value="False")]
        action_description.outcomes.append(outcome)
        self.action_descriptions[action_name]=action_description
    
    
    def add_door_model(self, forget_doors):
        rospy.loginfo("Adding doors")
        door_targets=[]
        for i in range(0,len(self.door_transitions)):
            transition = self.door_transitions[i]
            edge_id = self.door_transitions_edge_ids[i]
            #add stuff to model
            source=transition.pre_conds['waypoint']
            target=transition.prob_post_conds[0][1]['waypoint']
            source_wp=self.get_waypoint_prop(source)
            target_wp=self.get_waypoint_prop(target)
            if source in door_targets:
                index=door_targets.index(source)
                var_name="door_edge" + str(index)
                check_door_action_name='check_door' + str(index) + '_at_' + source_wp
                self.edge_to_door_dict[transition.action_name]=var_name
            else:
                door_targets.append(target)
                var_name="door_edge"+str(self.n_door_edges)
                self.edge_to_door_dict[transition.action_name]=var_name
                self.state_vars.append(var_name)
                self.state_vars_range[var_name]=(-1,1) #-1, unkown, 0 closed, 1 open
                self.initial_state[var_name]=-1
                check_door_action_name="check_door" + str(self.n_door_edges) + '_at_' + source_wp 
                self.actions.append(check_door_action_name)
                self.n_actions=self.n_actions+1
                self.n_door_edges=self.n_door_edges+1
            #update transition <- can only pass if door is open
            transition.pre_conds[var_name]=1            
            if forget_doors:
                #reset door value to -1
                for j in range(0, len(transition.prob_post_conds)):
                    transition.prob_post_conds[j][1][var_name]=-1
            #create check transition                
            self.transitions.append(MdpTransitionDef(action_name=check_door_action_name,
                                        pre_conds={'waypoint':source, var_name:-1},
                                        prob_post_conds=[[0.1,{'waypoint':source, var_name:0}],[0.9,{'waypoint':source, var_name:1}]],
                                        rewards={'time':self.door_timeouts[edge_id]*0.1+(self.door_timeouts[edge_id]*0.9)/2}))
            #add action description
            self.add_door_check_action_description(source_wp, target_wp, check_door_action_name, var_name, edge_id)
            
            #make all other nav transitions from source forget if door was open
            if forget_doors:
                extra_trans_list=[]
                for transition in self.transitions:
                    if transition not in self.door_transitions and transition.action_name in self.nav_actions and transition.pre_conds["waypoint"]==source:
                        trans_closed=deepcopy(transition)
                        trans_open=deepcopy(transition)
                        transition.pre_conds[var_name]=-1
                        trans_closed.pre_conds[var_name]=0
                        trans_open.pre_conds[var_name]=1
                        for j in range(0, len(transition.prob_post_conds)):
                            transition.prob_post_conds[j][1][var_name]=-1
                            trans_closed.prob_post_conds[j][1][var_name]=0
                            trans_open.prob_post_conds[j][1][var_name]=-1
                            extra_trans_list+=[trans_open, trans_closed]
                self.transitions+=extra_trans_list


    def string_int_pair_list_to_dict(self, string_int_pair_list):
        res={}
        for string_int_pair in string_int_pair_list:
            res[string_int_pair.string_data]=string_int_pair.int_data
        return res
    
    def action_msg_to_transition(self, action_msg, waypoint, use_expected_duration):
        pre_conds=self.string_int_pair_list_to_dict(action_msg.pre_conds)
        if waypoint is not None:
            pre_conds["waypoint"]=self.get_waypoint_var_val(waypoint)
        post_conds=[]
        total_prob=0
        for outcome in action_msg.outcomes:
            total_prob+=outcome.probability
            post_cond=self.string_int_pair_list_to_dict(outcome.post_conds)
            if outcome.waypoint != '':
                post_cond["waypoint"]=self.get_waypoint_var_val(outcome.waypoint)
            post_conds.append([outcome.probability, post_cond])
        if total_prob !=1:
            rospy.logerr("Probabilities of action outcomes don't add up to 1")
        
        if use_expected_duration:
            expected_duration=0
            for outcome in action_msg.outcomes:
                for (dur_prob, dur_val) in zip(outcome.duration_probs, outcome.durations):
                    expected_duration+=outcome.probability*dur_prob*dur_val
        else:
            rospy.logerr("Clustered times not supported yet...")
                    
        return MdpTransitionDef(action_name=action_msg.name,
                                    pre_conds=pre_conds,
                                    prob_post_conds=post_conds,
                                    rewards={"time":expected_duration})
    
    
    def add_extra_domain(self, var_list, action_list, use_expected_duration=True):
        for var in var_list:
            self.n_state_vars+=1
            self.state_vars.append(var.name)
            self.initial_state[var.name]=var.init_val
            self.state_vars_range[var.name]=[var.min_range, var.max_range]
        
        for action in action_list:
            self.action_descriptions.update({action.name:action})
            if action.waypoints==[]:
                self.transitions.append(self.action_msg_to_transition(action, None, use_expected_duration))
            for waypoint in action.waypoints:
                self.transitions.append(self.action_msg_to_transition(action, waypoint, use_expected_duration))
                                            
    def add_predictions(self, file_name, epoch=None, set_initial_state=True):
        if epoch is None:
            epoch=rospy.Time.now()
        if self.last_prediction_epoch is None or self.last_prediction_epoch - epoch >  self.get_new_preds_threshold or epoch - self.last_prediction_epoch > self.get_new_preds_threshold:
            self.add_nav_predictions(epoch)
            self.last_prediction_epoch = epoch
            if self.explicit_doors:
                self.add_door_predictions(epoch)
        self.write_prism_model(file_name, set_initial_state)

    def add_nav_predictions(self, epoch):
        try:
            predictions=self.get_edge_estimates(epoch)
            if len(predictions.edge_ids) != len(self.nav_actions):
                rospy.logwarn("Did not receive nav expectations for all edges, the total navigation expected values will not be correct")
            self.update_trans_with_nav_predictions(self.transitions, predictions)
            self.update_trans_with_nav_predictions(self.nav_template["transitions"], predictions)
        except rospy.ServiceException, e:
            rospy.logwarn("Error calling edge transversal times prediction service: " + str(e))
            rospy.logwarn("The total navigation expected values will not be for the requested epoch.")

    def update_trans_with_nav_predictions(self, transitions, predictions):
        for (edge, prob, duration) in zip(predictions.edge_ids, predictions.probs, predictions.durations):
            for transition in transitions:
                if edge == transition.action_name:
                    good_outcome = dict(transition.prob_post_conds[0][1])
                    if prob < 1:
                        if self.model_fatal_fails:
                            fatal_outcome = deepcopy(transition.pre_conds)
                            fatal_outcome['waypoint'] = -1
                            transition.prob_post_conds = [(prob, good_outcome), (1 - prob, fatal_outcome)]
                        else:
                            transition.prob_post_conds = [(prob, good_outcome), (1 - prob, dict(transition.pre_conds))]
                    else:
                        transition.prob_post_conds = [[1, good_outcome]]
                    if duration.to_sec > 0:
                        transition.rewards["time"] = duration.to_sec()
                    else:
                        rospy.logwarn("Edge predictions outputting negative travel time expectations. Ignoring...")

    def add_door_predictions(self, epoch):
        try:
            predictions=self.get_door_estimates(epoch)
            if len(predictions.edge_ids) != self.n_door_edges:
                rospy.logwarn("Did not receive expectations for all doors, the total navigation expected values will not be correct")
            self.update_trans_with_door_predictions(self.transitions, predictions)
            self.update_trans_with_door_predictions(self.nav_template["transitions"], predictions)
        except rospy.ServiceException, e:
            rospy.logwarn("Error calling door expectations prediction service: " + str(e))
            rospy.logwarn("The total navigation expected values will not be for the requested epoch.")

    def update_trans_with_door_predictions(self, transitions, predictions):
        for (edge, prob, duration) in zip(predictions.edge_ids, predictions.probs, predictions.durations):
            try:
                door_var = self.edge_to_door_dict[edge]
                for transition in transitions:
                    if "check_door" in transition.action_name:
                        if transition.pre_conds.has_key(door_var) and transition.pre_conds[door_var] == -1:
                            if prob < 1:
                                transition.prob_post_conds=[[1-prob, {door_var:0}],[prob,{door_var:1}]]
                            else:
                                transition.prob_post_conds=[[1, {door_var:1}]]
                            if duration.to_sec() > 0:
                                transition.rewards["time"]=prob*duration.to_sec() + (1-prob)*self.door_timeouts[edge]
                            else:
                                 rospy.logwarn("Door predictions outputting negative door wait expectations. Ignoring...")
            except KeyError, e:
                rospy.logwarn("Unknown edge in door predictions: " + edge)


