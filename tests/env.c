#include <stdio.h>
#include <stdlib.h>

//extern char** environ;

#define printenv(name) printf("%s = %s\n",name, getenv(name))

#if defined(_WIN64) || defined(_WIN32)
#define SEP "\n"
#else
#define SEP "\r\n"
#endif



int main(int argc, char** argv)
{
    printf("content-type: text/html%s", SEP);
    printf("x-special: haha%s%s", SEP, SEP);

    printenv("SERVER_SOFTWARE");
    printenv("SERVER_NAME");
    printenv("SERVER_PORT");
    printenv("GATEWAY_INTERFACE");
    printenv("SERVER_PROTOCOL");
    printenv("REQUEST_METHOD");
    printenv("PATH_INFO");
    printenv("PATH_TRANSLATED");
    printenv("QUERY_STRING");
    printenv("REMOTE_ADDR");

    return 0;
}