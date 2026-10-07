/* Disposable Crew probe: local append only; no policy or model context output. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 2) return 0;
    char input[65536]; size_t used = 0;
    while (used < sizeof(input)-1) {
        ssize_t n = read(STDIN_FILENO, input+used, sizeof(input)-1-used);
        if (n <= 0) break;
        used += (size_t)n;
    }
    input[used] = 0;
    while (used && (input[used-1]=='\n' || input[used-1]=='\r')) input[--used]=0;
    struct timespec now; clock_gettime(CLOCK_REALTIME, &now);
    int fd = open(argv[1], O_WRONLY|O_CREAT|O_APPEND, 0600);
    if (fd >= 0) {
        struct timespec begin, current, pause = {.tv_sec=0,.tv_nsec=100000};
        clock_gettime(CLOCK_MONOTONIC,&begin);
        int locked=0;
        do {
            if (flock(fd, LOCK_EX|LOCK_NB)==0) {locked=1;break;}
            nanosleep(&pause,NULL);
            clock_gettime(CLOCK_MONOTONIC,&current);
        } while ((current.tv_sec-begin.tv_sec)*1000000000LL+current.tv_nsec-begin.tv_nsec < 5000000LL);
        if (locked) {
            char prefix[128];
            int len = snprintf(prefix,sizeof(prefix),"{\"received_ns\":%lld,\"pid\":%d,\"payload\":",(long long)now.tv_sec*1000000000LL+now.tv_nsec,getpid());
            struct iovec vec[3]={{prefix,(size_t)len},{used ? input : "{}",used ? used : 2},{"}\n",2}};
            if (writev(fd,vec,3) < 0) fputs("Crew probe append failed\n",stderr);
            flock(fd,LOCK_UN);
        } else fputs("Crew probe append lock deadline exceeded\n",stderr);
        close(fd);
    }
    puts("{}");
    return 0;
}
