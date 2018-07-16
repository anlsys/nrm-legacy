#ifndef NRM_H
#define NRM_H 1

#include<time.h>

/* min time in nsec between messages: necessary for rate-limiting progress
 * report. For now, 10ms is the threashold. */
#define NRM_RATELIMIT_THRESHOLD (10000000LL)

struct nrm_context {
    void *context;
    void *socket;
    char *container_uuid;
    char *app_uuid;
    struct timespec time;
    unsigned long acc;
};

#define NRM_DEFAULT_URI "ipc:///tmp/nrm-downstream-in"
#define NRM_ENV_URI "ARGO_NRM_DOWNSTREAM_IN_URI"

#define NRM_START_FORMAT "{\"type\":\"application\", \"event\":\"start\", \"container\": \"%s\", \"uuid\": \"%s\", \"progress\": true, \"threads\": null}"
#define NRM_PROGRESS_FORMAT "{\"type\":\"application\", \"event\":\"progress\", \"payload\": \"%lu\", \"uuid\": \"%s\"}"
#define NRM_EXIT_FORMAT "{\"type\":\"application\", \"event\":\"exit\", \"uuid\": \"%s\"}"

int nrm_init(struct nrm_context *, const char *);
int nrm_fini(struct nrm_context *);

int nrm_send_progress(struct nrm_context *, unsigned long);

#endif
