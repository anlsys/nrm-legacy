/* Filename: downstream.c
 *
 * Description: This file contains the implementation of downstream API to
 * transmit application context information to NRM.
 *
 * The application context information transmitted can be used to monitor
 * application progress and/or invoke power policies to improve energy
 * efficiency at the node level.
 */

#include "downstream_api.h"
#include<zmq.h>
#include<stdio.h>
#include<unistd.h>
#include<string.h>
#include<stdlib.h>
#include<assert.h>

int nrm_init(struct nrm_context *ctxt, const char *uuid)
{
    assert(ctxt != NULL);
    assert(uuid != NULL);
    const char *uri = getenv(NRM_ENV_URI);
    if(uri == NULL)
        uri = NRM_DEFAULT_URI;
    ctxt->container_uuid = getenv("ARGO_CONTAINER_UUID");
    assert(ctxt->container_uuid != NULL);
    ctxt->app_uuid = (char *)uuid;
    ctxt->context = zmq_ctx_new();
    ctxt->socket = zmq_socket(ctxt->context, ZMQ_PUB);
    int err = zmq_connect(ctxt->socket, uri);
    assert(err == 0);
    char buf[512];
    snprintf(buf, 512, NRM_START_FORMAT, ctxt->container_uuid, ctxt->app_uuid);
    sleep(1);
    err = zmq_send(ctxt->socket, buf, strnlen(buf, 512), 0);
    assert(err > 0);
    assert(!clock_gettime(CLOCK_REALTIME, &ctxt->time));
    ctxt->acc = 0;
    return 0;
}

int nrm_fini(struct nrm_context *ctxt)
{
    assert(ctxt != NULL);
    char buf[512];
    snprintf(buf, 512, NRM_EXIT_FORMAT, ctxt->app_uuid);
    int err = zmq_send(ctxt->socket, buf, strnlen(buf, 512), 0);
    assert(err > 0);
    zmq_close(ctxt->socket);
    zmq_ctx_destroy(ctxt->context);
    return 0;
}

int nrm_send_progress(struct nrm_context *ctxt, unsigned long progress)
{
    char buf[512];
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    long long int timediff = (now.tv_nsec - ctxt->time.tv_nsec) +
                 1e9* (now.tv_sec - ctxt->time.tv_sec);
    ctxt->acc += progress;
    if(timediff > NRM_RATELIMIT_THRESHOLD) 
    {
        snprintf(buf, 512, NRM_PROGRESS_FORMAT, ctxt->acc, ctxt->app_uuid);
        int err = zmq_send(ctxt->socket, buf, strnlen(buf, 512), 0);
        assert(err > 0);
        ctxt->acc = 0;
    }
    ctxt->time = now;
    return 0;
}

int nrm_send_phase_context(struct nrm_context *ctxt, int cpu, unsigned long 
        long int startCompute, unsigned long long int endCompute, unsigned 
        long long int startBarrier, unsigned long long int endBarrier)
{
    char buf[512];
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    long long int timediff = (now.tv_nsec - ctxt->time.tv_nsec) +
                 1e9* (now.tv_sec - ctxt->time.tv_sec);

    if(timediff > NRM_RATELIMIT_THRESHOLD) 
    {
        snprintf(buf, 512, NRM_PHASE_CONTEXT_FORMAT, cpu, startCompute, 
                endCompute, startBarrier, endBarrier, ctxt->app_uuid);
        int err = zmq_send(ctxt->socket, buf, strnlen(buf, 512), 0);
        assert(err > 0);
    }
    ctxt->time = now;
    return 0;  
}
