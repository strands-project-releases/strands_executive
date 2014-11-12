/**
  This class contains methods to determine, which tasks are overlapping, and it establishes the pairs - containing tasks' ids.

  @author Lenka Mudrova
  @version 1.0 29/10/2014
*/
#include "pairs.h"
#include "task.h"
#include <vector>
#include <iostream> 
#include <algorithm>


using namespace std;

/**
  A constructor - initialise the set of tasks
  @param a set of tasks to use
  @return - nan, it is a constructor 
*/
Pairs::Pairs(vector<Task *> * input_tasks)
{
  tasksToS = input_tasks;
  numTasks = tasksToS -> size();
  numPairs = 0;
}

/**
  return determined pairs
  @param a pointer to the vector with pairs
  @return nothing
*/
void Pairs::getPairs(vector<vector<int>> * rp)
{
  *rp = pairs;
}

/**
  This method determines pairs based on the Brian Coltin's article - Dynamic User Task Scheduling for Mobile Robots (2011)
  @param none
  @return number of determined pairs
*/
int Pairs::setPairs_BC()
{
  vector<vector<int>>::iterator it;
  vector<int> opairs(4);  //one pair, always containing two integers (tasks' ids) + an order of a pair, when setted by the preVar method + the type of the pair

  //setting pairs based on the fact if their windows are overlapping. Thus, we need to decide if i precede j, or j precede i
  for (int i=0; i<numTasks; i++)
  {
    for (int j=i+1; j<numTasks; j++)
    {

      bool set = false;
      double ei = tasksToS->at(i)->getEnd();
      double si = tasksToS->at(i)->getStart();
      double ej = tasksToS->at(j)->getEnd();
      double sj = tasksToS->at(j)->getStart();

      double overlap = min(ei,ej) - max(si,sj);

      //I before J, or I after J there is no overlap and we dont want to add the pair.
      //for other cases, we would like to add some constraint
             
      if(overlap > 0)
      {
         opairs[0] = i;
         opairs[1] = j;
         opairs[2] = -1;
         opairs[3] = 2;  //2 - any combination of tasks is possible 
         set = true;     
      }
      
       if(set)
       {
         it = pairs.begin() + numPairs;
         pairs.insert(it,opairs);
         numPairs++;
       }
    }
  }
  return numPairs;
}

/**
  For intervals, where both options (I precedes J, J precedes I) are logically possible (equal, i during j, j during i), 
  we would like to test, if time, which is needed for travel, doesnt exclude one option
  @param pointers to task I and J, time neded to travel from I to J, from J to I
  @return the type of a pair
*/
int decidedInterval(Task * i, Task * j, double distij, double distji)
{
  double si = i->getStart();
  double ei = i->getEnd();
  double di = i->getDuration();

  double sj = j->getStart();
  double ej = j->getEnd();
  double dj = j->getDuration();

  double ij = di+dj+distij;
  double ji = di+dj+distji;

  //old version
  //double overlap = min(ei,ej) - max(si,sj);
  double overlap1 = ej-si;
  double overlap2 = ei-sj;

  
  if((ij<=overlap1)&&(ji<=overlap2)) //both combinations are possible
  {
    return 2;
  }
  else
  {
    if(ij<=overlap1) //only combination that i precedes j is possbile during overlap
    {
      return 1;
    }
    else if(ji<=overlap2) //only combination that j precedes i
    {
      return 0;
    }
    else
    {
      return -1; //there is a flaw in input data, both combinations are not possible
    }
  }


}

/**
  If both situations (I precedes J, J precedes I) are still possible, we simly choose one which minimises the time to execute both tasks
  @param time needed to execute I precedes J, time needed to execute J precedes I
  @return the chosen type of the pair
*/

int chooseInt(int time_ij, int time_ji)
{
  if(time_ij < time_ji)
  {
    return 1;
  }
  else
  {
    return 0;
  }
}

/**
  This method is mine proposed approach, which sets the pairs according Allen's interval algebra
  @param a pointer to 2d array of computed distances (this save a computation time)
  @return number of determined pairs
*/
int Pairs::setPairs_new(double ** dist_a)
{
  vector<vector<int>>::iterator it;
  vector<int> opairs(4);  //one pair, always containing two integers + order of pair, when setted by preVar method + the type of pair

  //setting pairs based on the fact if their windows are overlapping. Thus we need to decide if i precede j, or j precede i
  for (int a=0; a<numTasks; a++)
  {
    for (int b=a+1; b<numTasks; b++)
    {

      bool set = false;
      Task * i = tasksToS->at(a);
      Task * j = tasksToS->at(b);

      double ei = i->getEnd();
      double si = i->getStart();
      double di = i->getDuration();
      double ej = j->getEnd();
      double sj = j->getStart();
      double dj = j->getDuration();

      double distij = dist_a[a][b];
      double distji = dist_a[b][a];

      double time_ij = si+di+distij - sj;
      double time_ji = sj+dj+distji - si;

      if (time_ij <0)
        time_ij = 0;
      if (time_ji <0)
        time_ji = 0;
       
      //the combination of tasks is possible
      opairs[0] = a;//tasksToS->at(i)->getID();
      opairs[1] = b;//tasksToS->at(j)->getID();
      opairs[2] = -1; // this will be set in preVar method
      opairs[3] = -1;


      /*
      I before J, or I after J there is no overlapp and we dont want to add any constrain
      If task I ends after task J starts, 
      thus they overlap in certain way, 
      and we need to add constrain to ensure, that their execution will not overlap*/
      if(ei>sj) 
      {        
        //i overlaps j
        if((si<sj)&&(ei<ej))
        {
          opairs[3] = 1;          
          set = true;
        }
        
        //i starts j, equal
        else if(si==sj)
        {
          if(ei<ej) //i starts j
          {
            opairs[3] = 1; 
            set = true;
          }
          
          else if (ei==ej)//equals
          {
            /*
            the pair should be of type 2 (any combination), but if intervals are same and we are not using any priority, 
            it makes no sense to chose ordering, 
            however, dist(i,j) or dist(j,i) can be different and they might change the ordering. 
            Thus, we decide here which is the best ordering */
            opairs[3]=decidedInterval(i,j,distij, distji);
            if(opairs[3] == 2)
              opairs[3] = chooseInt(time_ij, time_ji);
        
            set = true;
          }
        }
       //j during i
        else if((si<sj)&&(ei>ej))
        {
           //both options (i precedes j, j precedes i) are generally possible
           opairs[3]=decidedInterval(i,j,distij, distji);
           //this is really pruning
            if(opairs[3] == 2)
              opairs[3] = chooseInt(time_ij, time_ji);
           set = true;
        }
        //i finish j
        else if((ei == ej)&&(si<sj))
        {
          opairs[3]=1; 
          set = true;
        }
      }
      if(ej>si)
      {
        //j overlaps i
        if((sj<si)&&(ej<ei))
        {
          opairs[3] = 0; 
          set = true;
        }
        
        else if((si==sj)&&(ej < ei)) //i imeets j
        {
          opairs[3]= 0; 
          set = true;
        }
       //i during j
        else if((sj<si)&&(ej>ei))
        {
          opairs[3]= decidedInterval(i,j,distij, distji);
          //this is really pruning
          if(opairs[3] == 2)
            opairs[3] = chooseInt(time_ij, time_ji);
          set = true;
        }
        else if((ei == ej)&&(sj<si))
        {
          opairs[3]= 0;
          set = true;
        }
      }
       if(set)
       {
         it = pairs.begin() + numPairs;
         pairs.insert(it,opairs);
         numPairs++;
  
       }

    }
  }
  return numPairs;
}
