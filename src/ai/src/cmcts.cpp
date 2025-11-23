#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <vector>
#include <stack>
#include <queue>
#include <string.h>
#include <algorithm>
#include <math.h>
#include <climits>
#include <array>
#include <omp.h>
#include <cstdlib>
#include <windows.h>
#include <ctime>    // 用于 clock_t 和 clock()
#include <random>

static const int BOARD_SIZE = 10;
static const int BOARD_GRID_SIZE = 100;
static const int EMPTY = 0;           // 空位
static const int RED_QUEEN = 1;       // 红方皇后
static const int BLUE_QUEEN = 2;      // 蓝方皇后
static const int STONE = 3;           // 障碍石头
static const int RED_SIDE = 1;        // 红方
static const int BLUE_SIDE = -1;      // 蓝方

static const int UCT_SELECT_NUMBER = 250; // UCT保留的节点数
static const int UCT_START_NUMBER = 5;//UCT一开始扩展的节点数
static const int UCT_ADD_WIDTH = 5;//UCT每1000次渐进拓宽的个数
static const int UCT_MAX_ATTEMPT_NUMBER = 5000000;//最大对局次数


static int dx[8] = { -1, -1, 0, 1, 1, 1, 0, -1 };
static int dy[8] = { 0, -1, -1, -1, 0, 1, 1, 1 };

static const bool isLegalArr[][12] = {
    {false,false,false,false,false,false,false,false,false,false,false,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,false,false,false,false,false,false,false,false,false,false,false}
};

//using boardArray = std::array<std::array<int, BOARD_SIZE>, BOARD_SIZE>;
//using queenArray = std::array<std::array<int, 4>, 2>;
using boardArray = int[BOARD_SIZE][BOARD_SIZE];
using queenArray = int[2][4];
namespace py = pybind11;
struct MoveAction {
    int From;
    int To;
    int Stone;
};

struct MoveValue {
    MoveAction action;
    double value;
};

struct MoveMessage
{
    int side;
    double value;
    double r;
};

struct MovePro
{
    int win;
    int attempt;
    //double pro;
};

struct UCTNode
{
    MoveAction action;
    MoveMessage message;
    MovePro simulate;

    std::vector<MoveValue> vecMovePos;
    int expandSize;
    int maxSize;
    int depth;

    UCTNode* parent;
    std::vector<UCTNode*> vecNodes;

    boardArray nodeBoard;
    queenArray queenPos;
};

struct UctRes {
    int From;
    int To;
    int Stone;
    int attempt;
    double value;
    double pro;
};

struct COMP {
    bool operator()(MoveValue const& a, MoveValue const& b) {
        return a.value > b.value;
    }
};

//初始化相关
void initBoard(boardArray& board);
void initQueenPos(queenArray& queenPos);
void displayBoard(const boardArray& board);

//走法生成与规则相关
void updateQueenPos(queenArray& queenPos, int moveSide, int from, int to);
bool isWin(const boardArray& board, queenArray& queenPos, int moveSide);
bool isNeighborsHaveEmpty(const boardArray& board, int actionFrom);
std::vector<int> getExpandTerritory(const boardArray& board, int actionFrom);
std::vector<MoveAction> getSideQueenOneMoveAction(const boardArray& board, const queenArray& queenPos, int moveSide);
std::vector<MoveValue> getSideQueenMoveAction(boardArray& board, const  queenArray& queenPos, int moveSide);
void checkDisplayMoveValue(const std::vector<MoveValue>& vecMoveValue);
std::vector<MoveValue> getSideQueenMoveValue(boardArray& board,const queenArray& queenPos, int moveSide);

//估值相关
double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide, double* wValue);
double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide);
double valueT2(const boardArray& board, const queenArray& queenPos, int moveSide);
double valueMobility(const boardArray& board,const queenArray& queenPos, int moveSide);
int getNeighborsEmptyNumber(const boardArray& board, int actionFrom);
int getNeighborsEmptyNumber(const boardArray& board, int fromX, int fromY);
double calculateOneQueenMobilityValue(const boardArray& board, int kingPosX, int kingPosY);
double valueAll(const boardArray& board, const queenArray& queenPos, int moveSide);

//uct相关
UCTNode* uctInitNode(const boardArray& board, const queenArray& queenPos, UCTNode* head, int moveSide);
void deleteRoot(UCTNode* node);
UCTNode* uctSelect(UCTNode* node);
double uctGetR(UCTNode* node);
int uctSimulate(const boardArray& board, const queenArray&, int moveSide);
void uctBackPropagation(UCTNode* node, int isWin);
UCTNode* uctExpand(UCTNode* node);
UctRes  uctAll(const boardArray& board, const queenArray&, int moveSide, double calTime = 1.0, bool isDisplayInfo = false);
void InitializeRandomSeed();

///////////////////////////////////////////////////具体实现
void initBoard(boardArray& board) {
    for (int i = 0; i < BOARD_SIZE; i++) {
        for (int j = 0; j < BOARD_SIZE; j++) {
            board[i][j] = EMPTY;
        }
    }
    //放置蓝方皇后
    board[0][3] = BLUE_QUEEN;
    board[0][6] = BLUE_QUEEN;
    board[3][0] = BLUE_QUEEN;
    board[3][9] = BLUE_QUEEN;

    //放置红方皇后
    board[6][0] = RED_QUEEN;
    board[6][9] = RED_QUEEN;
    board[9][3] = RED_QUEEN;
    board[9][6] = RED_QUEEN;
}

void initQueenPos(queenArray& queenPos) {
    //初始化蓝方皇后位置
    queenPos[1][0] = 3;
    queenPos[1][1] = 6;
    queenPos[1][2] = 30;
    queenPos[1][3] = 39;

    //初始化红方皇后位置
    queenPos[0][0] = 60;
    queenPos[0][1] = 69;
    queenPos[0][2] = 93;
    queenPos[0][3] = 96;
}

//控制台显示棋盘
void displayBoard(const boardArray& board)
{
    //打印行号
    std::cout << "\n\n   ";
    for (int i = 0; i < BOARD_SIZE; i++)
    {
        std::cout << i << "  ";
    }
    std::cout << std::endl << std::endl;

    //循环打印
    for (int i = 0; i < BOARD_SIZE; i++)
    {
        std::cout << i << "  "; //打印列号
        for (int j = 0; j < BOARD_SIZE; j++)
        {
            switch (board[i][j])
            {
            case EMPTY:
                std::cout << "_  ";
                break;
            case RED_QUEEN:
                std::cout << "R  ";
                break;
            case BLUE_QUEEN:
                std::cout << "B  ";
                break;
            case STONE:
                std::cout << "S  ";
                break;
            default:
                std::cout << "?  ";
                break;
            }
        }
        std::cout << std::endl << std::endl;
    }
}

void updateQueenPos(queenArray& queenPos, int moveSide, int from, int to) {
    //根据moveSide找到对应的皇后位置数组索引
    int sideIndex = (moveSide == RED_SIDE) ? 0 : 1;

    //找到from位置对应的皇后索引
    for (int i = 0; i < 4; ++i) {
        if (queenPos[sideIndex][i] == from) {
            queenPos[sideIndex][i] = to;
            break;
        }
    }
}

//是否获胜
bool isWin(const boardArray& board, queenArray& queenPos, int moveSide)
{
    int offset = moveSide == RED_SIDE ? 1 : 0;//判断反方

    for (int i = 0; i < 4; i++)
    {
        if (isNeighborsHaveEmpty(board, queenPos[offset][i]) == true)
        {
            return false;
        }
    }
    return true;
}

bool isNeighborsHaveEmpty(const boardArray& board, int actionFrom) {
    int fromX = actionFrom / BOARD_SIZE;
    int fromY = actionFrom % BOARD_SIZE;

    // 遍历邻居
    for (int i = 0; i < 8; ++i) {
        int toX = fromX + dx[i];
        int toY = fromY + dy[i];

        // 检查坐标是否越界
        if (toX >= 0 && toX < BOARD_SIZE && toY >= 0 && toY < BOARD_SIZE && board[toX][toY] == EMPTY) {
            return true; // 如果有一个空位置，就返回true
        }
    }

    return false; // 如果没有空位置，就返回false
}

std::vector<int> getExpandTerritory(const boardArray& board, int actionFrom) {
    std::vector<int> expandPos;

    int fromX = actionFrom / BOARD_SIZE;
    int fromY = actionFrom % BOARD_SIZE;

    // 检查所有方向的扩展
    for (int i = 0; i < 8; i++) {
        int x = fromX + dx[i];
        int y = fromY + dy[i];

        while (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY) {
            expandPos.push_back(x * BOARD_SIZE + y);
            x += dx[i];
            y += dy[i];
        }
    }

    return expandPos;
}

std::vector<MoveAction> getOneQueenMove(const boardArray& board, int actionFrom) {
    std::vector<MoveAction> moves;
    std::vector<int> expandPositions = getExpandTerritory(board, actionFrom);

    // 为每个扩展位置生成移动动作
    for (int expandPos : expandPositions) {
        std::vector<int> stonePositions = getExpandTerritory(board, expandPos);

        for (int stonePos : stonePositions) {
            MoveAction action;
            action.From = actionFrom;
            action.To = expandPos;
            action.Stone = stonePos;
            moves.push_back(action);
        }
    }

    return moves;
}

std::vector<MoveAction> getSideQueenOneMoveAction(const boardArray& board, const queenArray& queenPos, int moveSide) {
    std::vector<MoveAction> vecGetMovePos;
    int offset = moveSide == RED_SIDE ? 0 : 1;
    int tempChess = moveSide == RED_SIDE ? RED_QUEEN : BLUE_QUEEN;


    for (int k = 0; k < 4; k++)
    {
        int fromX = queenPos[offset][k] / BOARD_SIZE;
        int fromY = queenPos[offset][k] % BOARD_SIZE;


        for (int i = 0; i < 8; i++) {
            int x = fromX + dx[i];
            int y = fromY + dy[i];

            while (isLegalArr[x+1][y+1] && board[x][y] == EMPTY) {
                vecGetMovePos.push_back({queenPos[offset][k],x * BOARD_SIZE + y,-1});

                x += dx[i];
                y += dy[i];
            }
        }
    }

    return vecGetMovePos;
}

std::vector<MoveValue> getSideQueenMoveAction(boardArray& board,const queenArray& queenPos, int moveSide)
{
    std::vector<MoveValue> vecGetMovePos;
    int offset = moveSide == RED_SIDE ? 0 : 1;
    int tempChess = moveSide == RED_SIDE ? RED_QUEEN : BLUE_QUEEN;


    for (int k = 0; k < 4; k++)
    {
        int fromX = queenPos[offset][k] / BOARD_SIZE;
        int fromY = queenPos[offset][k] % BOARD_SIZE;
        //让当前皇后为空
        board[fromX][fromY] = EMPTY;
        //int tempQueenPos = queenPos[offset][k];

        for (int i = 0; i < 8; i++) {
            int x = fromX + dx[i];
            int y = fromY + dy[i];

            while (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY) {//x >= 0 && x < BOARD_SIZE  && y >= 0 && y < BOARD_SIZE
                // board[x][y] = tempChess;////
                 //updateQueenPos(queenPos, moveSide, queenPos[offset][k], x * BOARD_SIZE + y);////
                 //放障碍
                for (int j = 0; j < 8; j++) {
                    int stoneX = x + dx[j];
                    int stoneY = y + dy[j];


                    while (isLegalArr[stoneX + 1][stoneY + 1] && board[stoneX][stoneY] == EMPTY) {
                        //board[stoneX][stoneY] = STONE;//
                        vecGetMovePos.push_back({ {queenPos[offset][k],x * BOARD_SIZE + y,stoneX * BOARD_SIZE + stoneY},0.0 });
                        //vecGetMovePos.push_back({ {tempQueenPos,x * BOARD_SIZE + y,stoneX * BOARD_SIZE + stoneY},valueT1(board,queenPos,moveSide) });
                        //
                        board[stoneX][stoneY] = EMPTY;//
                        stoneX += dx[j];
                        stoneY += dy[j];
                    }
                }
                //board[x][y] = EMPTY;////
                //updateQueenPos(queenPos, moveSide, x * BOARD_SIZE + y ,queenPos[offset][k]);////
                x += dx[i];
                y += dy[i];
            }
        }
        board[fromX][fromY] = tempChess;
    }

    return vecGetMovePos;
}

std::vector<MoveValue> getSideQueenMoveValue(boardArray& board,const queenArray& queenPos, int moveSide)
{
    std::vector<MoveValue> vecSideMoveValue = getSideQueenMoveAction(board, queenPos, moveSide);
    //int tempBoard[10][10];
    //memccpy(tempBoard,board,100*4);

    const int num_moves = vecSideMoveValue.size();

    // 预计算所有坐标
    struct MoveCoord {
        int fromX, fromY, toX, toY, stoneX, stoneY;
    };
    std::vector<MoveCoord> coords;
    coords.reserve(num_moves);

    for (const auto& move : vecSideMoveValue) {
        coords.push_back({
            move.action.From / BOARD_SIZE,
            move.action.From % BOARD_SIZE,
            move.action.To / BOARD_SIZE,
            move.action.To % BOARD_SIZE,
            move.action.Stone / BOARD_SIZE,
            move.action.Stone % BOARD_SIZE
            });
    }

    int max_threads = omp_get_num_procs();
    omp_set_num_threads(max_threads);
    #pragma omp parallel for shared(vecSideMoveValue)
    for (int i = 0; i < vecSideMoveValue.size(); i++)
    {
        //boardArray tempBoard = board;
        //queenArray tempQueenPos = queenPos;
        boardArray tempBoard;
        queenArray tempQueenPos;
        memcpy(tempBoard,board,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
        memcpy(tempQueenPos,queenPos,sizeof(int)*8);//复制当前红方皇后位置


        const auto& coord = coords[i];

        //下一步棋
        //tempBoard[vecSideMoveValue[i].action.To / BOARD_SIZE][vecSideMoveValue[i].action.To % BOARD_SIZE] = tempBoard[vecSideMoveValue[i].action.From / BOARD_SIZE][vecSideMoveValue[i].action.From % BOARD_SIZE];
        //tempBoard[vecSideMoveValue[i].action.From / BOARD_SIZE][vecSideMoveValue[i].action.From % BOARD_SIZE] = EMPTY;
        //tempBoard[vecSideMoveValue[i].action.Stone / BOARD_SIZE][vecSideMoveValue[i].action.Stone % BOARD_SIZE] = STONE;

        tempBoard[coord.toX][coord.toY] = tempBoard[coord.fromX][coord.fromY];
        tempBoard[coord.fromX][coord.fromY] = EMPTY;
        tempBoard[coord.stoneX][coord.stoneY] = STONE;

        //updateQueenPos(tempQueenPos,moveSide,vecSideMoveValue[i].action.From,vecSideMoveValue[i].action.To);
        updateQueenPos(tempQueenPos, moveSide, vecSideMoveValue[i].action.From, vecSideMoveValue[i].action.To);

        vecSideMoveValue[i].value = valueAll(tempBoard, tempQueenPos, moveSide);//valueAll(tempBoard, tempQueenPos, moveSide);


        //updateQueenPos(tempQueenPos,moveSide, vecSideMoveValue[i].action.To, vecSideMoveValue[i].action.From);

        //还原这步棋
        //(*tempBoard)[vecSideMoveValue[i].action.Stone] = EMPTY;
        //(*tempBoard)[vecSideMoveValue[i].action.From] = (*tempBoard)[vecSideMoveValue[i].action.To];
        //(*tempBoard)[vecSideMoveValue[i].action.To] = EMPTY;
    }

    return vecSideMoveValue;

}

void checkDisplayMoveValue(const std::vector<MoveValue>& vecMoveValue)
{
    for (int i = 0; i < vecMoveValue.size(); i++){
        printf("\n%4d. From:%2d  To:%2d  Stone:%2d Value:%f", i + 1, vecMoveValue[i].action.From, vecMoveValue[i].action.To, vecMoveValue[i].action.Stone, vecMoveValue[i].value);
    }
}

double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide, double* wValue)
{
    double value = 0;
    int tempRedDisBoard[BOARD_GRID_SIZE] = { 0 };
    int tempBlueDisBoard[BOARD_GRID_SIZE] = { 0 };
    std::queue<int> queueRed, queueBlue;

    for (int i = 0; i < 4; ++i) {
        queueRed.push(queenPos[0][i]);
        queueBlue.push(queenPos[1][i]);
    }

    // BFS实现
    auto bfs = [&](std::queue<int>& q, int* distBoard) {
        int d = 1;
        while (!q.empty()) {
            int size = q.size();
            for (int i = 0; i < size; ++i) {
                int pos = q.front();
                q.pop();
                int fromX = pos / BOARD_SIZE;
                int fromY = pos % BOARD_SIZE;
                for (int j = 0; j < 8; ++j) {
                    int x = fromX + dx[j];
                    int y = fromY + dy[j];
                    int newPos = x * BOARD_SIZE + y;
                    while (isLegalArr[x + 1][y + 1] && distBoard[newPos] >= d) {
                        if (distBoard[newPos] > d) {
                            distBoard[newPos] = d;
                            q.push(newPos);
                        }
                        x += dx[j];
                        y += dy[j];
                        newPos = x * BOARD_SIZE + y;
                    }
                }
            }
            ++d;
        }
        };

    int count = 0;
    for (int i = 0; i < BOARD_SIZE; ++i)
    {
        for (int j = 0; j < BOARD_SIZE; ++j)
        {
            if (board[i][j] == EMPTY)
            {
                tempRedDisBoard[count] = INT_MAX;
                tempBlueDisBoard[count] = INT_MAX;
                count++; continue;
            }
            else {
                count++;
            }
        }
    }

    bfs(queueRed, tempRedDisBoard);
    bfs(queueBlue, tempBlueDisBoard);

    double w = 0;
    for (int i = 0; i < BOARD_GRID_SIZE; ++i) {
        if (tempRedDisBoard[i] < tempBlueDisBoard[i]) {
            value += 1;
        }
        else if (tempRedDisBoard[i] > tempBlueDisBoard[i]) {
            value -= 1;
        }

        if (tempRedDisBoard[i] == INT_MAX || tempBlueDisBoard[i] == INT_MAX)
        {
            w += 0;
        }
        else
        {
            w += pow(2.0, -abs(tempRedDisBoard[i] - tempBlueDisBoard[i]));
        }
    }
    *wValue = w;
    return moveSide == RED_SIDE ? value : -value;
}

double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    double w;
    return valueT1(board, queenPos, moveSide, &w);
}


double valueT2(const boardArray& board,const queenArray& queenPos, int moveSide)
{
    double value = 0;
    int tempRedDisBoard[BOARD_GRID_SIZE] = { 0 };
    int tempBlueDisBoard[BOARD_GRID_SIZE] = { 0 };
    std::queue<int> queueRed, queueBlue;

    for (int i = 0; i < 4; ++i) {
        queueRed.push(queenPos[0][i]);
        queueBlue.push(queenPos[1][i]);
    }

    auto bfs = [&](std::queue<int>& q, int* distBoard) {
        int d = 1;
        while (!q.empty()) {
            int size = q.size();
            for (int i = 0; i < size; ++i) {
                int pos = q.front();
                q.pop();
                int fromX = pos / BOARD_SIZE;
                int fromY = pos % BOARD_SIZE;
                for (int j = 0; j < 8; ++j) {
                    int x = fromX + dx[j];
                    int y = fromY + dy[j];
                    int newPos = x * BOARD_SIZE + y;

                    if (isLegalArr[x + 1][y + 1] && distBoard[newPos] >= d) {
                        if (distBoard[newPos] > d) {
                            distBoard[newPos] = d;
                            q.push(newPos);
                        }
                    }
                }
            }
            ++d;
        }
        };

    int count = 0;
    for (int i = 0; i < BOARD_SIZE; ++i)
    {
        for (int j = 0; j < BOARD_SIZE; ++j)
        {
            if (board[i][j] == EMPTY)
            {
                tempRedDisBoard[count] = INT_MAX;
                tempBlueDisBoard[count] = INT_MAX;
                count++; continue;
            }
            else {
                count++;
            }
        }
    }

    bfs(queueRed, tempRedDisBoard);
    bfs(queueBlue, tempBlueDisBoard);

    for (int i = 0; i < BOARD_GRID_SIZE; ++i) {
        if (tempRedDisBoard[i] < tempBlueDisBoard[i]) {
            value += 1;
        }
        else if (tempRedDisBoard[i] > tempBlueDisBoard[i]) {
            value -= 1;
        }
    }

    return moveSide == RED_SIDE ? value : -value;
}




double calculateOneQueenMobilityValue(const boardArray& board, int kingPosX, int kingPosY)
{
    int count;
    int N;
    int maxCount = 3;
    double mobilityValue = 0;
    //正左
    count = 1;
    while ((kingPosY - count) >= 0 && board[kingPosX][kingPosY - count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, kingPosX, (kingPosY - count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //左上

    count = 1;
    while ((kingPosX - count) >= 0 && (kingPosY - count) >= 0 && board[kingPosX - count][kingPosY - count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX - count), (kingPosY - count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //正上
    count = 1;
    while ((kingPosX - count) >= 0 && board[kingPosX - count][kingPosY] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX - count), kingPosY);
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //右上
    count = 1;
    while ((kingPosX - count) >= 0 && (kingPosY + count) <= 9 && board[kingPosX - count][kingPosY + count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX - count), (kingPosY + count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //正右
    count = 1;
    while ((kingPosY + count) <= 9 && board[kingPosX][kingPosY + count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, kingPosX, (kingPosY + count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //右下
    count = 1;
    while ((kingPosX + count) <= 9 && (kingPosY + count) <= 9 && board[kingPosX + count][kingPosY + count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX + count), (kingPosY + count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //正下
    count = 1;

    while ((kingPosX + count) <= 9 && board[kingPosX + count][kingPosY] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX + count), kingPosY);
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //左下
    count = 1;

    while ((kingPosX + count) <= 9 && (kingPosY - count) >= 0 && board[kingPosX + count][kingPosY - count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX + count), (kingPosY - count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }

    return mobilityValue;
}

double valueMobility(const boardArray& board,const queenArray& queenPos, int moveSide) {
    double valueMRed[4] = { 0 }, valueMBlue[4] = { 0 };


    for (int i = 0; i < 4; i++) {
        int kingPosX = queenPos[0][i] / BOARD_SIZE;
        int kingPosY = queenPos[0][i] % BOARD_SIZE;
        valueMRed[i] = calculateOneQueenMobilityValue(board, kingPosX, kingPosY);
    }

    for (int i = 0; i < 4; i++) {
        int kingPosX = queenPos[1][i] / BOARD_SIZE;
        int kingPosY = queenPos[1][i] % BOARD_SIZE;
        valueMBlue[i] = calculateOneQueenMobilityValue(board, kingPosX, kingPosY);
    }

    double mobilityValue = 0;

    for (int i = 0; i < 4; i++) {
        if (valueMBlue[i] <= 5) {
            mobilityValue += -0.4 * valueMBlue[i] + 7;
        }
        else {
            mobilityValue += 85.0 / (12 + valueMBlue[i]);
        }
        if (valueMRed[i] <= 5) {
            mobilityValue -= -0.4 * valueMRed[i] + 7;
        }
        else {
            mobilityValue -= 85.0 / (12 + valueMRed[i]);
        }
    }

    return (moveSide == RED_SIDE) ? mobilityValue : -mobilityValue;
}

// 获得某一点周围一圈邻接为空的个数
int getNeighborsEmptyNumber(const boardArray& board, int actionFrom)
{
    int count = 0;

    int fromX = actionFrom / BOARD_SIZE;
    int fromY = actionFrom % BOARD_SIZE;
    for (int i = 0; i < 8; ++i) {
        int x = fromX + dx[i];
        int y = fromY + dy[i];
        if (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY)
        {
            count++;
        }
    }
    return count;
}

// 获得某一点周围一圈邻接为空的个数
int getNeighborsEmptyNumber(const boardArray& board, int fromX, int fromY)
{
    int count = 0;

    for (int i = 0; i < 8; ++i) {
        int x = fromX + dx[i];
        int y = fromY + dy[i];
        if (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY)
        {
            count++;
        }
    }
    return count;
}

double valueAll(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    double value = 0;
    double w = 0;
    double t1 = valueT1(board, queenPos, moveSide, &w);
    double t2 = valueT2(board, queenPos, moveSide);
    double m = valueMobility(board, queenPos, moveSide);

    double k1, k2, k3;
    if (w >= 0 && w <= 14) {
        k1 = 1; k2 = 0; k3 = 0;
    }
    else if (w > 14 && w <= 25) {
        k1 = 1; k2 = 0; k3 = 0.2;
    }
    else if (w > 25 && w <= 40) {
        k1 = 1; k2 = 1; k3 = 1;
    }
    else if (w > 40 && w <= 55) {
        k1 = 1; k2 = 1; k3 = 2;
    }
    else if (w > 55 && w <= 63) {
        k1 = 1; k2 = 1; k3 = 3;
    }
    else {
        k1 = 1; k2 = 1; k3 = 4;
    }

    return t1 * k1 + t2 * k2 + k3 * m;
}



void deleteRoot(UCTNode* node)
{
    if (node == NULL)
    {
        return;
    }

    if (node->vecNodes.empty() != true)
    {
        for (int i = 0; i < node->vecNodes.size(); i++)
        {
            deleteRoot(node->vecNodes[i]);
        }
        delete(node);
    }
    else
    {

        delete(node);

    }
}

//初始化结点
UCTNode* uctInitNode(const boardArray& board, const queenArray& queenPos, UCTNode* head, int moveSide)
{
    head = new UCTNode;

    head->action.From = -1;
    head->action.To = -1;
    head->action.Stone = -1;

    head->message.side = -moveSide;
    head->message.value = valueAll(board, queenPos, -moveSide);
    head->message.r = 0;

    head->simulate.win = 0;
    head->simulate.attempt = 0;
    //head->simulate.pro = 0;

    head->expandSize = 0;
    head->depth = 0;

    head->parent = NULL;

    //head->nodeBoard = board;
    //head->queenPos = queenPos;

    memcpy(head->nodeBoard,board,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
    memcpy(head->queenPos,queenPos,sizeof(int)*8);//复制当前红方皇后位置


    return head;
}

//UCT算法的选择
UCTNode* uctSelect(UCTNode* node)
{
    UCTNode* currentPtr = node;

    while (!currentPtr->vecNodes.empty()) {
        if (currentPtr->expandSize < currentPtr->maxSize && (currentPtr->simulate.attempt / 1000 + 1) * UCT_ADD_WIDTH + UCT_START_NUMBER > currentPtr->expandSize) {
            uctExpand(currentPtr);
        }

        UCTNode* bestNode = nullptr;
        double bestR = -1.1;

        for (int i = 0; i < currentPtr->vecNodes.size(); i++) {
            double tempR = uctGetR(currentPtr->vecNodes[i]);
            currentPtr->vecNodes[i]->message.r = tempR;

            if (tempR > bestR) {
                bestR = tempR;
                bestNode = currentPtr->vecNodes[i];
            }
        }

        currentPtr = bestNode;
    }

    return currentPtr;
}

//得到r值
double uctGetR(UCTNode* node)
{
    double win = (node->simulate.win + node->simulate.attempt) / 2;

    return (double)win / node->simulate.attempt + 0.35 * (double)sqrt((double)log(node->parent->simulate.attempt) / node->simulate.attempt);
}

//UCT算法的扩展
UCTNode* uctExpand(UCTNode* node)
{
    UCTNode* currentPtr = node;
    int moveSide = -currentPtr->message.side;

    bool isSideWin = isWin(currentPtr->nodeBoard,currentPtr->queenPos,currentPtr->message.side);

    if(isSideWin)
    {
        uctBackPropagation(currentPtr,1);
        return currentPtr;
    }

    std::vector<MoveValue> vecMoveValue;


    if(node->simulate.attempt < 40 && node->simulate.attempt > 0)
    {
        //从我方下棋开始且最后我方输棋
        if(uctSimulate(node->nodeBoard,node->queenPos,-node->message.side) == node->message.side)
        {
            uctBackPropagation(node,1);
        }
        else//从我方下棋开始且最后对方输棋
        {
            uctBackPropagation(node,-1);
        }

        //OMPnRoundUCTSimulateSixStep(node,board,moveSide,4);

        return node;
    }

    /*if(node->depth == 8)
    {
        //从我方下棋开始且最后我方输棋
        if(uctSimulateSixStep(board,moveSide,6) == -moveSide)
        {
            uctBackPropagation(node,1);
        }
        else//从我方下棋开始且最后对方输棋
        {
            uctBackPropagation(node,-1);
        }

        return node;
    }*/


    int startNumber = node->expandSize;
    int endNumber;

    //节点是否为初始节点，只在扩展时模拟过一次
    if(node->vecMovePos.empty())
    {


        vecMoveValue = getSideQueenMoveValue(node->nodeBoard,node->queenPos,-node->message.side);

        //uctNodeNumber += vecMoveValue.size();

        //uctVecNumber++;
//uctAllValueNumber += vecMoveValue.size();

        std::sort(vecMoveValue.begin(),vecMoveValue.end(),COMP());//按价值从大到小排序


        if(vecMoveValue.size() >= UCT_SELECT_NUMBER)
        {
            vecMoveValue.erase(vecMoveValue.begin()+UCT_SELECT_NUMBER ,vecMoveValue.end());
            node->maxSize = UCT_SELECT_NUMBER;
            //checkDisplayMoveValue(vecSideMoveValue);
        }
        else
        {
            node->maxSize = vecMoveValue.size();
        }

        node->vecMovePos = vecMoveValue;


        endNumber =  UCT_START_NUMBER >= node->maxSize ? node->maxSize : UCT_START_NUMBER;

        node->expandSize = endNumber;

    }
    else
    {
        vecMoveValue = node->vecMovePos;

        endNumber = (node->expandSize + UCT_ADD_WIDTH) >= node->maxSize ? node->maxSize : (node->expandSize + UCT_ADD_WIDTH);

        node->expandSize = endNumber;
    }

    //checkDisplayMoveValue(vecMoveValue);

    for (int i = startNumber; i < endNumber; i++)
    {
        UCTNode* newNode = new UCTNode;
        //uctNodeNumber++;
        //newNode->nodeBoard = node->nodeBoard;
        //newNode->queenPos = node->queenPos;
        memcpy(newNode->nodeBoard,node->nodeBoard,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
        memcpy(newNode->queenPos,node->queenPos,sizeof(int)*8);//复制当前红方皇后位置

        //移动皇后与放置障碍
        newNode->nodeBoard[vecMoveValue[i].action.To / BOARD_SIZE][vecMoveValue[i].action.To % BOARD_SIZE] = newNode->nodeBoard[vecMoveValue[i].action.From / BOARD_SIZE][vecMoveValue[i].action.From % BOARD_SIZE];
        newNode->nodeBoard[vecMoveValue[i].action.From / BOARD_SIZE][vecMoveValue[i].action.From % BOARD_SIZE] = EMPTY;
        newNode->nodeBoard[vecMoveValue[i].action.Stone / BOARD_SIZE][vecMoveValue[i].action.Stone % BOARD_SIZE] = STONE;

        //更新皇后位置
        updateQueenPos(newNode->queenPos, moveSide, vecMoveValue[i].action.From, vecMoveValue[i].action.To);

        newNode->action.From = vecMoveValue[i].action.From;
        newNode->action.To = vecMoveValue[i].action.To;
        newNode->action.Stone = vecMoveValue[i].action.Stone;
        newNode->parent = currentPtr;
        newNode->message.side = newNode->parent->message.side * -1;
        newNode->message.value = vecMoveValue[i].value;

        newNode->simulate.attempt = 0;
        newNode->simulate.win = 0;
        newNode->message.r = -1;
        newNode->expandSize = 0;
        newNode->depth = newNode->parent->depth + 1;

        if (newNode->message.value >= 0)
        {
            uctBackPropagation(newNode, 1);
        }
        else
        {
            uctBackPropagation(newNode, -1);
        }


        node->vecNodes.push_back(newNode);
    }

    return currentPtr;
}


int uctSimulate(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    int randomIndex;
    int step;
    int tempSide = moveSide;

    std::vector<int> vecTemp;
    std::vector<MoveAction> vecMovePos;

    //boardArray temp_board = board;
    //queenArray temp_queenPos = queenPos;
    boardArray temp_board;
    queenArray temp_queenPos;
    memcpy(temp_board,board,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
    memcpy(temp_queenPos,queenPos,sizeof(int)*8);//复制当前红方皇后位置


    for (step = 0; step < 6; step++)
    {
        //下一步
        vecMovePos = getSideQueenOneMoveAction(temp_board, temp_queenPos, tempSide);

        if (vecMovePos.empty())
        {
            return -tempSide;
        }
        randomIndex = rand() % vecMovePos.size();

        //temp_board[vecMovePos[randomIndex].To / BOARD_SIZE][vecMovePos[randomIndex].To % BOARD_SIZE] = temp_board[vecMovePos[randomIndex].From / BOARD_SIZE][vecMovePos[randomIndex].From % BOARD_SIZE];
        //temp_board[vecMovePos[randomIndex].From / BOARD_SIZE][vecMovePos[randomIndex].From % BOARD_SIZE] = EMPTY;
        (*temp_board)[vecMovePos[randomIndex].To] = (*temp_board)[vecMovePos[randomIndex].From];
        (*temp_board)[vecMovePos[randomIndex].From] = EMPTY;

        updateQueenPos(temp_queenPos, tempSide, vecMovePos[randomIndex].From, vecMovePos[randomIndex].To);//更新皇后位置

        //放置障碍
        vecTemp = getExpandTerritory(temp_board, vecMovePos[randomIndex].To);

        if (!vecTemp.empty()) {
            randomIndex = rand() % vecTemp.size();
            temp_board[vecTemp[randomIndex] / BOARD_SIZE][vecTemp[randomIndex] % BOARD_SIZE] = STONE;
        }
        tempSide = -tempSide;
    }


    if (valueAll(temp_board, temp_queenPos, RED_SIDE) >= 0)
    {
        return RED_SIDE;
    }
    else
    {
        return BLUE_SIDE;
    }

}


/*
int uctSimulate(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    const int SIM_COUNT = 7;  // 并行模拟次数 = 线程数
    int redWins = 0;
    int blueWins = 0;

    // === OpenMP 并行模拟 ===
    #pragma omp parallel for num_threads(SIM_COUNT) reduction(+:redWins, blueWins)
    for (int sim = 0; sim < SIM_COUNT; ++sim)
    {
        // 独立复制棋盘和皇后位置
        boardArray temp_board;
        queenArray temp_queenPos;
        memcpy(temp_board, board, sizeof(int) * BOARD_GRID_SIZE);
        memcpy(temp_queenPos, queenPos, sizeof(int) * 8);

        int tempSide = moveSide;
        int randomIndex;
        std::vector<int> vecTemp;
        std::vector<MoveAction> vecMovePos;

        // 每线程独立随机种子（防止相同序列）
        srand((unsigned)time(NULL) + sim * 37 + omp_get_thread_num() * 13);

        for (int step = 0; step < 6; step++)
        {
            vecMovePos = getSideQueenOneMoveAction(temp_board, temp_queenPos, tempSide);
            if (vecMovePos.empty())
            {
                if (-tempSide == RED_SIDE)
                    redWins++;
                else
                    blueWins++;
                goto next_sim;
            }

            randomIndex = rand() % vecMovePos.size();

            (*temp_board)[vecMovePos[randomIndex].To] = (*temp_board)[vecMovePos[randomIndex].From];
            (*temp_board)[vecMovePos[randomIndex].From] = EMPTY;

            updateQueenPos(temp_queenPos, tempSide,
                           vecMovePos[randomIndex].From,
                           vecMovePos[randomIndex].To);

            vecTemp = getExpandTerritory(temp_board, vecMovePos[randomIndex].To);
            if (!vecTemp.empty())
            {
                randomIndex = rand() % vecTemp.size();
                temp_board[vecTemp[randomIndex] / BOARD_SIZE]
                          [vecTemp[randomIndex] % BOARD_SIZE] = STONE;
            }

            tempSide = -tempSide;
        }

        // 模拟结束后计算局面价值
        if (valueAll(temp_board, temp_queenPos, RED_SIDE) >= 0)
            redWins++;
        else
            blueWins++;

    next_sim:
        continue;
    }

    // === 汇总并返回结果 ===
    if (redWins >= blueWins)
        return RED_SIDE;
    else
        return BLUE_SIDE;
}*/

//UCT算法的反向传播
void uctBackPropagation(UCTNode* node, int isWin)
{
    UCTNode* currentNode = node;
    int winSide = node->message.side;


    //将win，attemp传播
    while (currentNode != NULL)
    {
        currentNode->simulate.attempt++;

        if (currentNode->message.side == winSide)
        {
            currentNode->simulate.win += isWin;
        }
        else
        {
            currentNode->simulate.win -= isWin;
        }

        currentNode = currentNode->parent;
    }

}

void InitializeRandomSeed() {
    LARGE_INTEGER nFrequency;
    if (::QueryPerformanceFrequency(&nFrequency)) {
        LARGE_INTEGER nStartCounter;
        ::QueryPerformanceCounter(&nStartCounter);
        ::srand(nStartCounter.QuadPart); // 使用整个 64 位值作为种子
    }
    else {
        SYSTEMTIME st;
        ::GetLocalTime(&st);
        unsigned int seed = st.wYear * 10000 + st.wMonth * 100 + st.wDay;
        seed = seed * 60000 + st.wHour * 1000 + st.wMinute * 60 + st.wSecond;
        seed = seed * 1000 + st.wMilliseconds; // 使用完整的系统时间作为种子
        ::srand(seed);
    }
}

//uct算法
UctRes  uctAll(const boardArray& board,const queenArray& queenPos, int moveSide, double calTime,bool isDisplayInfo)
{


    //displayBoard(board);

    double uctTime = calTime;

    int maxAttempt = 0;
    double useTime;
    UctRes bestMoveInfo;

    /*if(isAllQuennSureTerritory(board) == true)
    {
        cout << "<isAllQuennSureTerritory>\n";
        uctTime = 5;
    }*/


    UCTNode* uctTree = NULL;

    uctTree = uctInitNode(board, queenPos, uctTree, moveSide);

    clock_t startTime = clock();

    while (1)
    {
        UCTNode* selectNode = uctSelect(uctTree);
        UCTNode* maxNode = uctExpand(selectNode);

        clock_t endTime = clock();

        useTime = (double)(endTime - startTime) / CLOCKS_PER_SEC;

        if (useTime > uctTime || uctTree->simulate.attempt > UCT_MAX_ATTEMPT_NUMBER)
        {
            if (uctTree->vecNodes.empty() == true)
            {
                system("pause");
            }

            UCTNode* bestNode = uctTree->vecNodes[0];

            maxAttempt = bestNode->simulate.attempt;

            int bestNumber = 0;

            for (int i = 0; i < uctTree->vecNodes.size(); i++)
            {
                int tempAttempt = uctTree->vecNodes[i]->simulate.attempt;

                if (tempAttempt > maxAttempt)
                {
                    bestNode = uctTree->vecNodes[i];
                    maxAttempt = tempAttempt;
                    bestNumber = i;
                }
            }



            bestMoveInfo.From = bestNode->action.From;
            bestMoveInfo.To = bestNode->action.To;
            bestMoveInfo.Stone = bestNode->action.Stone;
            bestMoveInfo.attempt = bestNode->parent->simulate.attempt;
            bestMoveInfo.value = bestNode->message.value;
            bestMoveInfo.pro = ((double)(bestNode->simulate.win + bestNode->simulate.attempt) / bestNode->simulate.attempt / 2) * 100;
            //cout << uctTree->simulate.attempt;
            //uctDisplayUCTNode(uctTree);
            //double thisTime = (double)(endTime - startTime) / CLOCKS_PER_SEC;
            //allTime += thisTime;
            //printf("<This Time :%0.1fs. All time:%0.2fmin. Count:%d>",thisTime,allTime/60.0,moveCount);


            double uctPro = ((double)(bestNode->simulate.win + bestNode->simulate.attempt) / bestNode->simulate.attempt / 2) * 100;


            if (isDisplayInfo)
            {
                double  w = 0;
                valueT1(board, queenPos, moveSide, &w);



                if (moveSide == RED_SIDE)
                {
                    printf("red");
                }
                else
                {
                    printf("blue");
                }


                printf("(From:%d,To:%d,Stone:%d)|%f|", bestNode->action.From, bestNode->action.To, bestNode->action.Stone, w);
                printf("(attemp:%d/%d,number: %d/%d,value:%.2f,pro:%0.0f)\n", bestNode->simulate.attempt, uctTree->simulate.attempt, bestNumber, uctTree->vecNodes.size(),
                    bestNode->message.value, ((double)(bestNode->simulate.win + bestNode->simulate.attempt) / bestNode->simulate.attempt / 2) * 100);
                //printf("(|%.0f|[%d/%d][value:%.2f][%0.0f]\n",checkW(board),bestNode->simulate.attempt,uctTree->simulate.attempt,
                       //bestNode->message.value,( (double)(bestNode->simulate.win + bestNode->simulate.attempt)/bestNode->simulate.attempt/2 )*100);

                //winPos = ( (double)(bestNode->simulate.win + bestNode->simulate.attempt)/bestNode->simulate.attempt/2 )*100;
            }

            deleteRoot(uctTree);
            break;
        }
    }


    return bestMoveInfo;
}

// 辅助函数：将 py::array_t 转换为 C++ 静态数组 (10x10 board)
void convert_pyarray_to_carray(py::array_t<int> py_board, boardArray& c_board) {
    py::buffer_info buf = py_board.request();
    if (buf.ndim != 2 || buf.shape[0] != BOARD_SIZE || buf.shape[1] != BOARD_SIZE) {
        throw std::runtime_error("Board shape must be (10, 10)");
    }
    int *ptr = (int *)buf.ptr;
    // 使用 memcpy 比逐个赋值更快，但需要谨慎处理内存布局
    std::memcpy(c_board, ptr, sizeof(int) * BOARD_GRID_SIZE);
}

// 辅助函数：将 py::list 转换为 C++ 静态数组 (2x4 queenPos)
void convert_pylist_to_carray(py::list py_queens, queenArray& c_queens) {
    if (py_queens.size() != 2) {
        throw std::runtime_error("Queen positions must be a list of 2 lists/arrays.");
    }
    for (int side = 0; side < 2; ++side) {
        py::list side_queens = py_queens[side];
        if (side_queens.size() != 4) {
            throw std::runtime_error("Each side must have 4 queen positions.");
        }
        for (int i = 0; i < 4; ++i) {
            c_queens[side][i] = side_queens[i].cast<int>();
        }
    }
}



class AmazonasAI {
public:
    // 构造函数：无状态类，无需参数
    AmazonasAI() {
        InitializeRandomSeed();
    }
    ~AmazonasAI() {}

    // 核心函数：包装并调用原始的 uctAll
    UctRes uctSearch(py::array_t<int> initialBoard, py::list initialQueenPos, int moveSide, double calTime, bool isDisplayInfo) {
        // 1. 将 Python 数据结构转换为 C++ 静态数组
        boardArray board;
        queenArray queenPos;
        convert_pyarray_to_carray(initialBoard, board);
        convert_pylist_to_carray(initialQueenPos, queenPos);

        // 2. 调用原始的 uctAll 函数
        return uctAll(board, queenPos, moveSide, calTime, isDisplayInfo);
    }
};




// ===========================================
// pybind11 封装部分
// ===========================================
PYBIND11_MODULE(amazon_ai, m) {
    m.doc() = "pybind11 wrapper for the Amazonas UCT C++ AI"; // 模块文档字符串

    // 1. 绑定 UctRes 结构体
    py::class_<UctRes>(m, "UctRes")
        .def(py::init<>())
        .def_readwrite("From", &UctRes::From)
        .def_readwrite("To", &UctRes::To)
        .def_readwrite("Stone", &UctRes::Stone)
        // 绑定新增的成员
        .def_readwrite("attempt", &UctRes::attempt)
        .def_readwrite("value", &UctRes::value)
        .def_readwrite("pro", &UctRes::pro)
        .def("__repr__", [](const UctRes& a) {
            // 使用 std::ostringstream 构造更清晰的 repr 字符串，便于调试
            std::ostringstream os;
            os << "<UctRes From:" << a.From
               << " To:" << a.To
               << " Stone:" << a.Stone
               << " attempt:" << a.attempt
               << " value:" << a.value
               << " pro:" << a.pro << ">";
            return os.str();
        });

    // 2. 绑定 AmazonasAI 类
    py::class_<AmazonasAI>(m, "AmazonasAI")
        // 绑定无参数构造函数
        .def(py::init<>())
        // 绑定 uctSearch 函数
        .def("uct_search", &AmazonasAI::uctSearch,
             py::arg("initialBoard"),
             py::arg("initialQueenPos"),
             py::arg("moveSide"),
             py::arg("calTime"),
             py::arg("isDisplayInfo") = false, // 将可选参数 isDisplayInfo 绑定
             "Runs UCT/MCTS search on the given board state and returns the best move.")
        // 绑定 __repr__
        .def("__repr__", [](const AmazonasAI &a) {
            return "<AmazonasAI object>";
        });
}
