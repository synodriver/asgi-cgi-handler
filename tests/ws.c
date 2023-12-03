#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#define MB(x) x*1024*1024

#if defined(_WIN64) || defined(_WIN32)
#define SEP "\n"
#else
#define SEP "\r\n"
#endif

#define READLINE_BUFFSIZE 200
static char buf[READLINE_BUFFSIZE];  // for readline

// 返回buf的长度，代表一行数据
int freadline(FILE *f)
{
    int offset = 0;
    int ret = 0;
    while (fread(buf + offset, sizeof(char), 1, f))
    {
        char *sub; //
#if defined(_WIN64) || defined(_WIN32)
        if ((sub = memchr(buf, SEP[0], offset + 1))) // 找到 \n
        {
            ret = sub - (char *) buf;
            offset = 0;
            break;
        }
#else
        char * sub2;
        if ((sub=memchr(buf, SEP[0], offset+1))&&(sub2=memchr(buf, SEP[1],offset+1))&&((sub2-sub)==1)) // 找到 \r\n
        {
            ret =  sub-(char*)buf;
            offset = 0;
            break;
        }
#endif
        offset++;
        if (offset >= READLINE_BUFFSIZE) // 读了这么多字节还是没发现行 G
        {
            break;
        }
    }
    return ret;
}

int main(int argc, char **argv)
{
    for(;;)
    {
        char* line = fgets(buf,READLINE_BUFFSIZE, stdin);
        fwrite(line, sizeof(char), strlen(line)-strlen(SEP), stdout);
        fprintf(stdout, "%s", SEP);
        fflush(stdout);
    }
    return 0;
}