
#include <stdio.h>
#include <stdlib.h>
#include <beacon.h>
#include <string.h>

#include <powPerfController.h>

/* Baseline example to receive ERM power settings in the NRM */



// We need the hostname for the message filter in my_beacon_handler
// but would like to set it only once when the callback is set
// via set_nrm_power_target
static char hostname[100];



// We need a function pointer for the function to apply each time a
// new setting is received. set_nrm_power_target will set the value
// and my_beacon_handler() will use it
void (*target_handler)(double watts);
void set_nrm_power_target(void (*handler)(double watts));



/* BEACON boilerplate */
static int SET_NODE_E=2;



BEACON_beep_t binfo;
BEACON_beep_handle_t handle;
BEACON_subscribe_handle_t shandle1;
BEACON_topic_info_t *topic_info;
BEACON_topic_properties_t *eprop;

char data_buf[100];
char beep_name[100];
char filter_string[100];
char topic_string[32];


int BEACON_bcast_init() {
    eprop = (BEACON_topic_properties_t *) malloc(sizeof(BEACON_topic_properties_t));

    topic_info = (BEACON_topic_info_t *)malloc(sizeof(BEACON_topic_info_t));
    if(topic_info == NULL) {
        fprintf(stderr, "Malloc error!\n");
        exit(0);
    }

    strcpy(topic_info[0].topic_name, "BEACON_BROADCAST");
    sprintf(topic_info[0].severity, "INFO");
    printf("The %d topic is %s\n", 0, topic_info[0].topic_name);
    memset(&binfo, 0, sizeof(binfo));
    strcpy(binfo.beep_version, "1.0");
    strcpy(binfo.beep_name, "beacon_test");
    int ret = BEACON_Connect(&binfo, &handle);
    if (ret != BEACON_SUCCESS) {
        printf("BEACON_Connect is not successful ret=%d\n", ret);
        exit(-1);
    }

    strcpy(eprop->topic_scope, "global");
    return 1;
}



int is_SET_NODE(char* message, char* node, double* watts) {

    int mtype;
    int rc = sscanf(message, "message type=%d;", &mtype);
    if(rc!=1) {
       return 0;
    }

    if(mtype!=SET_NODE_E) {
        return 0;
    }

    rc = sscanf(message, "message type=%d ; node=%s ; target watts=%lf",&mtype, node, watts);
    if(rc!=3) {
        printf("wrong arg count %d\n",rc);
        return 0;
    }
    return 1;
}



pthread_t poll_thread;

void* poll_logic(void* args) {
    void (*handler)(BEACON_receive_topic_t* caught_topic) = (void (*)(BEACON_receive_topic_t*))args;
    while(1) {
        BEACON_receive_topic_t caught_topic;
        int ret = BEACON_Wait_topic(shandle1, &caught_topic, 5);
        if (ret != BEACON_SUCCESS) {
            continue;
        }
        handler(&caught_topic);
    }
}


int BEACON_bcast_subscribe(void (*handler)()) {
    char* caddr = getenv("BEACON_TOPOLOGY_SERVER_ADDR");
    sprintf(filter_string, "cluster_addr=%s,cluster_port=10809,topic_scope=global,topic_name=%s", caddr, topic_info[0].topic_name);
    int ret = BEACON_Subscribe(&shandle1, handle, 0, filter_string, NULL);
    pthread_create(&poll_thread, NULL, poll_logic, handler);
}



// The callback to send with the subscription

void my_beacon_handler(BEACON_receive_topic_t* topic) {
    char node[100];
    double watts;
    // parse string store parts in enclave and delta
    if(is_SET_NODE(topic->topic_payload, node, &watts)) {
        if(strcmp(node,hostname)==0) {
            target_handler(watts);
        }
    }
}

/* End boilerplate */





// Test handler to show that we can receive readings

//void test_handler(double watts) {
 //   printf("got %lf watts\n",watts);
//}



// The function that connects to BEACON and sets up the message handling

void set_nrm_power_target(void (*handler)(double watts)) {
    gethostname(hostname,100);
    BEACON_bcast_init();
    target_handler=handler;
    BEACON_bcast_subscribe(my_beacon_handler);
}



// A simple main function that runs the process for about a minute

//int main(int argc, char** argv) {
  //  set_nrm_power_target(test_handler);
  //  sleep(30);
//}
