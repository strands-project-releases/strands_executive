import rospy
from datetime import datetime, timedelta
from dateutil.tz import tzlocal, tzutc
from copy import copy

from threading import Thread

_epoch = datetime.utcfromtimestamp(0).replace(tzinfo=tzutc())

class RoutineException(Exception): 
    pass

def unix_time(dt):
    """
    Converts a datetime object to seconds since epoch
    """    
    delta = dt - _epoch
    return delta.total_seconds()

def time_to_secs(time):
    """ 
    Coverts a datetime.time object to seconds.
    """
    return (time.hour * 60 * 60) + (time.minute * 60) + (time.second) + (time.microsecond/1000.0)
	
    # start by providing bounds on daily exectuion

    # given a task or list of tasks (which could be produce by that task at all waypoints)

    # do it n times in a specific window,  - scheduled for proposal x secs before the window

    # do it n times every X duration 

def start_of_the_day(day_delta=0): 
    """
        Get the datetime at the start of the day requested, i.e. the last midnight which has passed. All done in UTC

        Args:
            day_delta (int, optional): The relative day to today. 0 is today, 1 is tomorrow, -1 is yesterday. Defaults to 0.
        Returns:
            datetime.datetime: The date time at the start of the day 
    """
    return datetime.fromordinal(datetime.utcfromtimestamp(rospy.get_rostime().to_sec()).toordinal() + day_delta).replace(tzinfo=tzutc())

def time_less_than(t1, t2):
    """ Seems to be a bug in datetime when comparing localtz dates, so do this instead. """
    if t1.hour < t2.hour:
        return True
    elif t1.hour == t2.hour:
        if t1.minute < t2.minute:
            return True 
        elif t1.minute == t2.minute:
            if t1.second < t2.second:
                return True
            elif t1.second == t2.second:
                return t1.microsecond < t2.microsecond

    return False


class DailyRoutine(object):
    """ An object for setting up the daily schedule of a robot. 
        Args:
            daily_start (datetime.time): The time of day when all tasks can start, local time.
            daily_end (datetime.time): The time of day by when all tasks should end, local time.
            pre_start_window (datetime.timedelta): The duration before a task's start that it should be passed to the scheduler. Defaults to 1 hour.
    """
    def __init__(self, daily_start, daily_end):
        super(DailyRoutine, self).__init__()
        self.daily_start = daily_start
        self.daily_end = daily_end
        self.routine_tasks = []
    


    def repeat_every_day(self, tasks, times=1):
        """
        Repeat the given tasks a number of times during the day.
        """
        self.repeat_every(tasks, self.daily_start, self.daily_end, times)

    def repeat_every_mins(self, tasks, mins=30, times=1):
        """
        Repeat the given tasks x times every n minutes
        """

        window_start = self.daily_start
        new_end_mins = window_start.minute + mins
        if new_end_mins <= 59: 
            window_end =  window_start.replace(minute=(new_end_mins))
        else:
            window_end =  window_start.replace(minute=(new_end_mins-59), hour=(window_start.hour + 1))

        while window_end <= self.daily_end:

            if window_start == window_end:
                return
           
            print '%s.%s - %s.%s' % (window_start.hour, window_start.minute, window_end.hour, window_end.minute)
            self.repeat_every(tasks, window_start, window_end, times)
    

            window_start = window_end

            new_end = window_start
            new_end_mins = new_end.minute + mins
            if new_end_mins <= 59: 
                new_end =  new_end.replace(minute=(new_end_mins))
            else:                
                new_end =  new_end.replace(minute=(new_end_mins-59), hour=(new_end.hour + 1))

            if new_end.hour < 23:
                window_end = new_end
            else:
                window_end = self.daily_end 


    def repeat_every_hour(self, tasks, hours=1, times=1):
        """
        Repeat the given tasks x times every n hours
        """

        window_start = self.daily_start
        window_end =  window_start.replace(hour=(window_start.hour + hours))

        while window_end <= self.daily_end:

            if window_start == window_end:
                return
           
            # print '%s.%s - %s.%s' % (window_start.hour, window_start.minute, window_end.hour, window_end.minute)
            self.repeat_every(tasks, window_start, window_end, times)
    

            window_start = window_end
            if window_start.hour + hours < 23:
                window_end =  window_start.replace(hour=(window_start.hour + hours))
            else:
                window_end = self.daily_end 


    def repeat_every(self, tasks, daily_start, daily_end, times=1):
        """
        Repeat the given task a number of times during the day.
        """

        # make tasks a list if its not already 
        if not isinstance(tasks, list):            
            tasks = [tasks]

        self.routine_tasks += [(tasks, (daily_start, daily_end))] * times

    def get_routine_tasks(self):
        return self.routine_tasks


class DailyRoutineRunner(object):
    """ An object for running the daily schedule of a robot. 
        Args:
            daily_start (datetime.time): The time of day when all tasks can start, local time.
            daily_end (datetime.time): The time of day by when all tasks should end, local time.
            pre_start_window (datetime.timedelta): The duration before a task's start that it should be passed to the scheduler. Defaults to 1 hour.
    """
    def __init__(self, daily_start, daily_end, add_tasks_srv, pre_start_window=timedelta(hours=0.25), day_start_cb=None, day_end_cb=None, tasks_allowed_fn=None):
        super(DailyRoutineRunner, self).__init__()
        self.daily_start = daily_start
        self.daily_end = daily_end
        assert time_less_than(daily_start, daily_end)
        # the tasks which need to be performed every day, tuples of form (daily_start, daily_end, task)
        self.routine_tasks = []
        self.add_tasks_srv = add_tasks_srv

        if tasks_allowed_fn is None:
            self.tasks_allowed = self._tasks_allowed_fn
        else:
            self.tasks_allowed = tasks_allowed_fn

        self.days_off = []
        self.dates_off = []

        # check for local spellings!
        self.all_days = []
        day_today = datetime.fromtimestamp(rospy.get_rostime().to_sec(), tz=tzlocal())
        for n in range(0,7):
            self.all_days.append(day_today.strftime("%A"))
            day_today += timedelta(days=1)


        self.pre_schedule_delay = rospy.Duration(pre_start_window.total_seconds())
        self.midnight_thread = Thread(target=self._delay_to_midnight)
        self.midnight_thread.start()
        self.day_start_cb = day_start_cb
        self.day_end_cb = day_end_cb
        if day_start_cb != None or day_end_cb != None:
            Thread(target=self._start_and_end_day).start()

    def add_day_off(self, day_name):
        """ Add a day of the week, e.g. Saturday, on which the routing should not be run """
        if day_name not in self.all_days:
            raise Exception('Day name %s not allowed. Must be one of %s' % (day_name, self.all_days))
        self.days_off.append(day_name)

    def add_date_off(self, date):
        """ Add a datetime.date on which the robot should not work. """
        self.dates_off.append(date)

    def day_off(self):
        datetime_today = datetime.fromtimestamp(rospy.get_rostime().to_sec(), tz=tzlocal())
        day_today = datetime_today.strftime("%A")
        date_today = datetime_today.date()

        return (day_today in self.days_off) or (date_today in self.dates_off)

    def _tasks_allowed_fn(self):        
        return True

    def _start_and_end_day(self):
        """ Runs a loop which triggers the start and end of day callbacks """

        loop_delay = rospy.Duration(1)

        while not rospy.is_shutdown():
 
            # again, using sleeps rather than timers due to slightly odd sim time behaviour of the latter
            now = datetime.fromtimestamp(rospy.get_rostime().to_sec(), tz=tzlocal())
    
            # print('Now', now.time())
            # print('Now', self.daily_start)

            # wait for the start of the day
            while time_less_than(self.daily_start, now.time()) and time_less_than(self.daily_end, now.time()) and not rospy.is_shutdown():
                rospy.sleep(loop_delay)
                now = datetime.fromtimestamp(rospy.get_rostime().to_sec(), tz=tzlocal())

            while time_less_than(now.time(),self.daily_start) and not rospy.is_shutdown():                
                rospy.sleep(loop_delay)
                now = datetime.fromtimestamp(rospy.get_rostime().to_sec(), tz=tzlocal())

            if self.day_start_cb is not None and not rospy.is_shutdown():
                rospy.loginfo('triggering day start cb at %s' % now)
                self.day_start_cb()

            while time_less_than(now.time(),self.daily_end) and not rospy.is_shutdown():                
                rospy.sleep(loop_delay)
                now = datetime.fromtimestamp(rospy.get_rostime().to_sec(), tz=tzlocal())

            if self.day_end_cb is not None and not rospy.is_shutdown():
                rospy.loginfo('triggering day end cb at %s' % now)
                self.day_end_cb()



    def _delay_to_midnight(self):
        
        while not rospy.is_shutdown():

            # jump to the start of the next day in rostime
            midnight = start_of_the_day(1)
            print "midnight  %s" % midnight
            midnight_rostime = rospy.Time(unix_time(midnight))
            
            now = rospy.get_rostime()
            print "midnight_rostime  %s" % midnight_rostime.to_sec()
            print "             now  %s" % now.to_sec()
            assert midnight_rostime > now
                  
            while rospy.get_rostime() < midnight_rostime and not rospy.is_shutdown():
                rospy.sleep(1)

            if not rospy.is_shutdown():               
                print "MIDNIGHT %s" % datetime.fromtimestamp(rospy.get_rostime().to_sec())
                self._new_day()




    """
        Does some basic checking on the task.
        Args:
            daily_start (datetime.time): The time of day when the task can start.
            daily_end (datetime.time): The time of day by when the task should end.
    """
    def sanity_check_task(self, daily_start, daily_end, task):
        end_secs = time_to_secs(daily_end)
        start_secs = time_to_secs(daily_start)
        if end_secs <= start_secs:
            raise RoutineException('Task window is negative: %s to %s' % (daily_start, daily_end))
        if end_secs - start_secs < task.max_duration.secs:
            raise RoutineException('Task window is not large enough for task: %s to %s for task of duration %s' % (daily_start, daily_end, timedelta(seconds=task.max_duration)))


    """
        Adds a task to the daily routine.
        Args:
            routines: A list of tuples where each tuple is (task_list, window) where task_list is a list of task and window is a tuple (start, end) representing a time window in which to execute those tasks each day.
    """
    def add_tasks(self, routines):

        # add tasks to daily route
        new_routine = []
        for task_tuple in routines:
            
            daily_start = task_tuple[1][0]
            daily_end = task_tuple[1][1]

            for task in task_tuple[0]:
                # bound by daily activity window
                if time_less_than(daily_start, self.daily_start):
                    rospy.loginfo('Bounding task to daily start window')
                    daily_start = self.daily_start

                if time_less_than(self.daily_end, daily_end):
                    rospy.loginfo('Bounding task to daily end window')
                    daily_end = self.daily_end

                self.sanity_check_task(daily_start, daily_end, task)
        
                # else, add to daily routine
                routine = (daily_start, daily_end, task)
                self.routine_tasks.append(routine)
                new_routine.append(routine)

        # see if we can still schedule any of these today
        todays_tasks = self._instantiate_tasks_for_today(new_routine)
        # the false means an exception is not thrown for any out of window tasks
        self._create_routine(todays_tasks, False)

        
    def _new_day(self):
        """
            Should be called each new day, in advance of the overall daily start time.
        """

        todays_tasks = self._instantiate_tasks_for_today(self.routine_tasks)
        self._create_routine(todays_tasks)


    def _instantiate_tasks_for_today(self, routine_tasks):
        start_of_today = start_of_the_day()    
        # instantiate the daily tasks with release windows for today
        todays_tasks = [self._instantiate_for_day(start_of_today, *task_tuple) for task_tuple in routine_tasks]
        return todays_tasks

    def _create_routine(self, tasks, throw=True):

        schedule_now, schedule_later = self._queue_for_scheduling(tasks, throw)

        rospy.loginfo('Scheduling %s tasks now and %s later' % (len(schedule_now), len(schedule_later)))

        self._delay_tasks(schedule_later)
        self._schedule_tasks(schedule_now)


    def _delay_tasks(self, tasks):
        """
            Delays call to the scheduer until the first of these needs to start, then reruns check for scheduling
        """

        if len(tasks) == 0:
            return

        # find the soonest start date of all tasks

        # an arbitrary large date
        min_start_date = rospy.Time(unix_time(start_of_the_day(2)))
        for task in tasks:
            if task.start_after < min_start_date:           
                min_start_date = task.start_after 

        # only delay up to the pre-scheduler window 
        min_start_date = min_start_date - self.pre_schedule_delay

        now = rospy.get_rostime()

        # print 'min start at %s' % min_start_date.secs
        # print '      now at %s' % now.secs

        delay = min_start_date - now

        # print 'delaying %s' % delay.secs
        self._delay_scheduling(tasks, delay)


    # separated out to try differeing approaches
    def _delay_scheduling(self, tasks, delay):
        rospy.loginfo('Delaying %s tasks for %s secs' % (len(tasks), delay.secs))

        def _check_tasks():
            # using a sleep instead of a timer as the timer seems flakey with sim time            
            target = rospy.get_rostime() + delay
            # make sure we can be killed here
            while rospy.get_rostime() < target and not rospy.is_shutdown():
                rospy.sleep(1)
            # handle being shutdown
            if not rospy.is_shutdown():
                self._create_routine(tasks)

        Thread(target=_check_tasks).start()


    def _schedule_tasks(self, tasks):
        rospy.loginfo('Sending %s tasks to the scheduler' % (len(tasks)))
        if len(tasks) > 0:
            if not self.day_off() and self.tasks_allowed():
                self.add_tasks_srv(tasks)
            else:
                rospy.loginfo('Provided function prevented tasks being send to the scheduler')

    def _instantiate_for_day(self, start_of_day, daily_start, daily_end, task):
        """ 
            Create a copy of the given task with start and end times instantiated from input variables relative to the start date provided.
        """
        instantiated_task = copy(task)
        release_date = datetime.combine(start_of_day.date(), daily_start)
        end_date = datetime.combine(start_of_day.date(), daily_end)
        instantiated_task.start_after = rospy.Time(unix_time(release_date))
        instantiated_task.end_before = rospy.Time(unix_time(end_date))
        # print '%s (%s)' % (release_date, instantiated_task.start_after.secs)
        # print '%s (%s)' % (end_date, instantiated_task.end_before.secs)

        return instantiated_task


    def _queue_for_scheduling(self, tasks, throw=True):
        now = rospy.get_rostime()

        schedule_now = []
        schedule_later = []

        for task in tasks:

            # print task.max_duration.secs
            # print task.start_after.secs
            # print task.end_before.secs
            # print (now).secs
            # print (now + task.max_duration).secs


            # check we're not too late
            if now + task.max_duration > task.end_before:
                # 
                if throw:
                    raise RoutineException('%s is too late to schedule task %s' % (now.secs, task))
                else:
                    rospy.logdebug('Ignoring task for today')
            else:
                # if we're in the the window when this should be scheduled
                if now > (task.start_after - self.pre_schedule_delay):
                    schedule_now.append(task)
                else:
                    schedule_later.append(task)

        return schedule_now, schedule_later





