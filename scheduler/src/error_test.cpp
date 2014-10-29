#include "ros/ros.h"

#include <iostream>
#include <string>
#include <vector>

#include "task.h"
#include "scheduler.h"

using namespace std;

int main (int argc, char** argv) 
{   
  ros::init(argc, argv, "error_test");

  string s1("ChargingPoint");
  string s2("Lobby");

  int task_count = 4;

  double one_hour = 60 * 60 * 60;
  double task_duration = one_hour / 2.0;
  double nav_time = 300;
  double window_start = 0;
  double window_end = window_start + ((task_duration + nav_time) * task_count * task_count * task_count);

  vector<Task*> tasks;

  tasks.push_back(new Task(1, window_start, window_end, task_duration, s2, s2, true));
  tasks.push_back(new Task(2, window_start, window_end, task_duration, s1, s1));
  tasks.push_back(new Task(3, window_start, window_end, task_duration, s2, s2));
  


  Scheduler scheduler(&tasks);
  bool worked = scheduler.solve(4, "");

  if(worked)  {
    cout<< "Schedule found" << worked << "\n";
    for(auto & tp : tasks) {
      cout<<"task "<<tp->getID()<<endl;
      cout<< "start time "<<tp->getExecTime()<<endl;

    } 
  }
  else {
    cout<< "No schedule found"<< endl;
  }

  return 0;

}
