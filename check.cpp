#include <iostream>
#include <fstream>
#include <cstdio>
#include <string>
#include <iomanip>
using namespace std;

int main() {
    const int FILES = 10;
    const long long CHUNK = 4096; // 缓冲区大小，提高读效率

    for (int i = 0; i < FILES; ++i) {
        string fname1 = to_string(i) + ".txt";
        string fname2 = "ans" + to_string(i) + ".txt";

        ifstream fin1(fname1, ios::binary);
        ifstream fin2(fname2, ios::binary);

        if (!fin1.is_open() || !fin2.is_open()) {
            cerr << "无法打开文件: " << fname1 << " 或 " << fname2 << endl;
            continue;
        }

        long long total = 0, same = 0;
        char buf1[CHUNK], buf2[CHUNK];

        // 分块读入并比较
        while (!fin1.eof() && !fin2.eof()) {
            fin1.read(buf1, CHUNK);
            fin2.read(buf2, CHUNK);
            streamsize cnt1 = fin1.gcount();
            streamsize cnt2 = fin2.gcount();
            streamsize cnt = min(cnt1, cnt2);
            for (streamsize j = 0; j < cnt; ++j) {
                if (buf1[j] == buf2[j]) ++same;
            }
            total += cnt;
            // 如果两个文件块大小不一致，说明已有一个文件结束，跳出
            if (cnt1 != cnt2) break;
        }

        // 如果文件长度不一致，输出提示
        if (fin1.eof() != fin2.eof()) {
            cout << "警告: 文件 " << fname1 << " 与 " << fname2 << " 长度不一致，只比较了前 " << total << " 字节。" << endl;
        }

        fin1.close();
        fin2.close();

        double rate = (total == 0) ? 0.0 : (double)same / total * 100.0;
        cout << "[" << i << "] " << fname1 << " vs " << fname2
             << " : " << fixed << setprecision(2) << rate << "%"
             << " (" << same << "/" << total << ")" << endl;
    }

    return 0;
}
