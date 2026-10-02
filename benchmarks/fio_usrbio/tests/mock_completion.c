/* Local correctness fixture only; this mock performs no 3FS I/O. */
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "hf3fs_usrbio.h"
struct fixture_ring { int count; struct hf3fs_cqe completions[64]; };
int hf3fs_iorcreate3(struct hf3fs_ior *ior, const char *mount, int entries, bool read, int depth, int priority, int timeout, int numa) {
    (void)mount; (void)entries; (void)depth; (void)priority; (void)timeout; (void)numa;
    memset(ior, 0, sizeof(*ior)); ior->for_read=read;
    ior->iorh=calloc(1,sizeof(struct fixture_ring)); return ior->iorh?0:-ENOMEM;
}
int hf3fs_iorcreate(struct hf3fs_ior *ior, const char *mount, int entries, bool read, int depth, int numa) {
    return hf3fs_iorcreate3(ior,mount,entries,read,depth,0,1,numa);
}
void hf3fs_iordestroy(struct hf3fs_ior *ior) { free(ior->iorh); }
int hf3fs_iovcreate(struct hf3fs_iov *iov, const char *mount, size_t size, size_t block, int numa) {
    (void)mount; (void)block; (void)numa; memset(iov,0,sizeof(*iov));
    iov->base=malloc(size); iov->size=size; return iov->base?0:-ENOMEM;
}
void hf3fs_iovdestroy(struct hf3fs_iov *iov) { free(iov->base); }
int hf3fs_reg_fd(int fd, uint64_t flags) { (void)fd; (void)flags; return 0; }
void hf3fs_dereg_fd(int fd) { (void)fd; }
int hf3fs_prep_io(const struct hf3fs_ior *ior, const struct hf3fs_iov *iov, bool read, void *ptr, int fd, size_t off, uint64_t len, const void *userdata) {
    (void)iov; (void)read; (void)ptr; (void)fd; (void)off;
    struct fixture_ring *ring=ior->iorh;
    if(ring->count==64)return -ENOSPC;
    int index=ring->count++;
    static bool short_used=false;
    bool short_result=getenv("INJECT_USRBIO_SHORT") && !short_used;
    if(short_result)short_used=true;
    ring->completions[index]=(struct hf3fs_cqe){.index=index,.result=getenv("INJECT_USRBIO_ERROR")?-EIO:(int64_t)(short_result?len/2:len),.userdata=userdata};
    return index;
}
int hf3fs_submit_ios(const struct hf3fs_ior *ior) { (void)ior; return 0; }
int hf3fs_wait_for_ios(const struct hf3fs_ior *ior, struct hf3fs_cqe *cqes, int count, int min, const struct timespec *timeout) {
    (void)min; (void)timeout; struct fixture_ring *ring=ior->iorh;
    int ready=ring->count<count?ring->count:count;
    for(int i=0;i<ready;i++){
        cqes[i]=ring->completions[ready-1-i];
        const char *path=getenv("COMPLETION_FIXTURE_LOG");
        if(path){ FILE *file=fopen(path,"a"); if(file){fprintf(file,"%lld\n",(long long)cqes[i].result);fclose(file);} }
    }
    ring->count=0;return ready;
}
