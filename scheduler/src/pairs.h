//------------------------------
//guarding to avoid multiple including
#ifndef __PAIRS_H_INCLUDED__
#define __PAIRS_H_INCLUDED__

#include <vector>
class Task;

using namespace std;


class Pairs
{
  int numPairs;
  int numTasks;
  vector<vector<int>> pairs;
  vector<Task *> * tasksToS;
public:
  Pairs(vector<Task *> *);
  int setPairs();
  int setPairs_BC();
  int setPairs_mine();
  int setPairs_new();
  void getPairs(vector<vector<int>> *);
};


#endif
