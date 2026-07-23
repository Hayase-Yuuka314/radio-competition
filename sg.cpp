#include<iostream>
#include<cstdio>
#include<cstring>
#include<vector>
#include<algorithm>
#include<cmath>
#include<stdlib.h>
#include<queue>
#include<ctime>
#include<map>
#include<set>
#include<unordered_map>
#include<numeric>
const double down = 0.9997;
const int N = 10005;
const int M = 200005;
const double pp = 0.00000001;
const int mod = 1000000007;
using namespace std;
inline int read()
{
    int x=0,f=1;
    char ch=getchar();
    while(!isdigit(ch))
    {
        if(ch=='-')
            f=-1;
        ch=getchar();
    }
    while(isdigit(ch))
    {
        x=(x<<1)+(x<<3)+(ch^48);
        ch=getchar();
    }
    return x*f;
}
inline void write(int x){
    if(x<0) putchar('-'), x=-x;
    if(x>9) write(x/10);
    putchar(x%10+'0');
}
int main()
{
    srand(time(0));
    const long long total = 10000000;
    for (int file_id = 0; file_id < 10; ++file_id) {
        char filename[20];
        sprintf(filename, "%d.txt", file_id);
        FILE* f = fopen(filename, "w");
        if (!f) {
            printf("无法创建文件 %s\n", filename);
            return 1;
        }
        for (long long i = 0; i < total; ++i) {
            putc(rand() % 26 + 'A', f);
        }
        fclose(f);
        printf("文件 %s 生成完成\n", filename);
    }
    return 0;
}
