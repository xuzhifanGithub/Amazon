# 亚马逊棋Amazon-留白/闯关
  该项目是基于UCT(MCTS改进)的亚马逊棋博弈程序,获得2023年全国计算机博弈大赛亚马逊项目冠军，本应开源(我也想)，但出于大赛老师们希望大家独立制作的理念，便只对项目细节进行详细描述。大家实现后可下载可执行文件进行对比测试，水平相等或者强于则证明实现成功。
## 其他：作者另一个项目《基于深度强化学习的海克斯棋博弈系统》存在开源代码，地址如下：https://github.com/xuzhifanGithub/vsHexQL

## 目录
### 一.UCT算法改进（默认了解UCT）
  #### 1.延迟扩展：
  正常UCT算法模拟一次完毕后直接扩展结点，
  这会浪费时间和空间去大量扩展，故设置其模拟40次后再扩展结点。
  #### 2.估值筛选：
  亚马逊棋前期状态比较多，每次对所有可行位置去扩展会浪费大量时间。
  所以对全部可行位置进行估值排序筛选，选取前250个位置进行扩展。
  #### 3.渐进加宽：
  对于所有估值排序好的可行位置而言，若估值准确，排序在前面的位置则更可能为较优的位置。所以初始扩展结点只选取前5个位置，
  每当结点模拟次数增多1000次时则增加5个位置，直到全部扩展完毕。
  #### 4.分配时间：
  回合数    分配时间  
  01-10 --->       35s  
  10-20  --->      27s  
  20-30  --->      19s  
  30-46   --->     5s（双方圈地完毕也是5s）
  #### 5.提前评估：
  在UCT的模拟阶段，随机下棋6步（一步包括走子与放障碍）后进行局面评估，当前方估值大于0则返回胜利，反之失败.
  p.s.：  
  1）由于时间的关系，随机下棋分为俩小步来节约时间，先在所有皇后的可行走子中选一步移动，再随机选一处放障碍。  
  2）可以将估值映射到[-1,1]，此时相当于返回胜率，没试过但理论上应该可以。  
  3）尝试过随机下棋时走4,5,7,8等步数后评估，发现只有6最好。
  #### 6.继承搜索数：
  对于一次回合，己方最后能生成一棵搜索树，此时并不销毁，而是判断对方所下位置是否在搜索树的枝结点上，是的话便将此枝节点当根节点，继承部分搜索树。
  #### 7.挂起搜索
  当对面搜索时，己方可以对6中继承的搜索树进行扩展拓宽，充分利用时间，等到对面搜索完毕时己方则停止。
### 二.估值选用（默认了解估值）
 #### 1.选用估值：
 只选用t1，t2和m估值，不选c估值是因为手动调估值太累了，就不加了。  
 经测试，其中t1和t2估值当n = m < ∞ 时k = 0（即双方到达空格子的最小步数相同时，不计算该格），此时效果最好。
 #### 2.权重比例
此程序依据w来进行系数的调整。设t1，t2，m的系数分别为k1，k2，k3.  
 w -> (63,92] 时：k1 = 1, k2 = 1, k3 = 4(k3先手5，后手4)  
 w -> (55,63] 时：k1 = 1, k2 = 1, k3 = 3  
 w -> (40,55] 时：k1 = 1, k2 = 1, k3 = 2   
 w -> (25,40] 时：k1 = 1, k2 = 1, k3 = 1  
 w -> (14,25] 时：k1 = 1, k2 = 0, k3 = 0.2  
 w --> [0,14]  时：k1 = 1, k2 = 0, k3 = 0  
 不连续的估值可能会出现UCT显示的胜率断层般的升高或者降低(大部分情况下还是较为稳定的)，也尝试过连续但是效果并不行，就放弃了。
### 三.多线程应用
采用OpenMp编程模型，对程序进行加速。由于线程的建立和销毁也需要时间，  
故经过几处地方的实验，最终发现在获取一方所有可行位置的估值时应用最好。  
经实验，相同程序相同时间内采用8线程比单线程快3倍。
### 总结与展望
本文对invader程序进行实验与复现，最终能够在相同时间时成功打败它。  
如果制作引擎，在可读性较强的情况下1500行代码即可完成以上全部内容。
该程序有着较强的水平，但仍然具有不足，结合神经网络进行深度学习成为其下一步的方向。




  
  
  
  
  

