/* -*- Mode: C; c-basic-offset:4 ; indent-tabs-mode:nil ; -*- */
/*
 * See COPYRIGHT in top-level directory.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <poll.h>
#include <assert.h>

#include "common.h"
#include <powPerfController.h>

double power_cap;

static void handle_error(const char *msg);
static float get_power();


void test_handler(double watts) {
    power_cap=(float) watts;
    printf("new power_cap: %f watts\n",power_cap);

}

enum {
    CMD_INIT,
    CMD_INC_MODE,
    CMD_DEC_MODE,
};

int main(int argc, char *argv[])
{

    set_nrm_power_target(test_handler);


    int sockfd, port;
    struct sockaddr_in my_addr;
    struct sockaddr_in abt_addr;
    socklen_t addrlen;
    struct pollfd abt_pfd;

    //saeid 
    float current_power=0;
    power_cap=300;

    char send_buf[SEND_BUF_LEN];
    char recv_buf[RECV_BUF_LEN];
    int quit = 0;
    int abt_alive = 0;
    int n, ret;

    int cur_cmd_mode = CMD_INIT;
    int prv_cmd_mode;
    int cmd_failed = 0;
    int skip_cmd = 0;

    if (argc < 2) {
        fprintf(stderr, "Usage: %s <port> \n", argv[0]);
        exit(1);
    }
    port = atoi(argv[1]);
//    power_cap = atof(argv[2]);
    float threshold=0.10;



    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) handle_error("ERROR: socket");


    bzero((char *)&my_addr, sizeof(my_addr));
    my_addr.sin_family = AF_INET;
    my_addr.sin_addr.s_addr = INADDR_ANY;
    my_addr.sin_port = htons(port);
    ret = bind(sockfd, (struct sockaddr *)&my_addr, sizeof(my_addr));
    if (ret < 0) handle_error("ERROR: bind");

    while (!quit) {
        printf("Waiting for connection...\n");

        listen(sockfd, 5);
        addrlen = sizeof(abt_addr);
        abt_pfd.fd = accept(sockfd, (struct sockaddr *)&abt_addr, &addrlen);
        if (abt_pfd.fd < 0) handle_error("ERROR: accept");
        abt_pfd.events = POLLIN | POLLRDHUP;
        abt_alive = 1;


        printf("Client connected...\n\n");

        while (abt_alive) {

            current_power = get_power();
            printf("currnet power = %f, power_cap = %f\n",current_power,power_cap);

            prv_cmd_mode = cur_cmd_mode;
            if (current_power < ((1-threshold)* power_cap)){
                 bzero(send_buf, SEND_BUF_LEN);
                 send_buf[0] = 'i';
                 cur_cmd_mode = CMD_INC_MODE;
            }else if (current_power > ((1+threshold)* power_cap)){
                 bzero(send_buf, SEND_BUF_LEN);
                 send_buf[0] = 'd';
                 cur_cmd_mode = CMD_DEC_MODE;
            }else{
                // Sangmin - fix: we don't need to send a message to Argobots
                //bzero(send_buf, SEND_BUF_LEN);
                // send_buf[0] = 'n';
                skip_cmd = 1;
                cur_cmd_mode = CMD_INIT;
            }

            if (send_buf[0] != 'd' && send_buf[0] != 'i' &&
                send_buf[0] != 'n' && send_buf[0] != 'q') {
                printf("Unknown command: %s\n", send_buf);
                continue;
            }

            if (cur_cmd_mode == prv_cmd_mode && cmd_failed) {
                skip_cmd = 1;
            }

            if (skip_cmd) {
                skip_cmd = 0;
                sleep(1);
                continue;
            }

            n = write(abt_pfd.fd, send_buf, strlen(send_buf));
            assert(n == strlen(send_buf));

            bzero(recv_buf, RECV_BUF_LEN);

            /* Wait for the ack */
            printf("Waiting for the response...\n");
            while (1) {
                ret = poll(&abt_pfd, 1, 10);
                if (ret == -1) {
                    handle_error("ERROR: poll");
                } else if (ret != 0) {
                    if (abt_pfd.revents & POLLIN) {
                        n = read(abt_pfd.fd, recv_buf, RECV_BUF_LEN);
                        if (n < 0) handle_error("ERROR: read");

                        printf("Response: %s\n\n", recv_buf);
                        cmd_failed = strcmp(recv_buf, "failed") == 0;
                    }
                    if (abt_pfd.revents & POLLRDHUP) {
                        abt_alive = 0;
                        printf("Client disconnected...\n");
                        break;
                    }
                    abt_pfd.revents = 0;
                    break;
                }
            }

            if (send_buf[0] == 'q') {
                quit = 1;
                close(abt_pfd.fd);
                break;
            }
           //saeid, for checking sending/recieving is working correctly
           sleep(1);
        }
    }

    close(sockfd);

    return EXIT_SUCCESS;
}

/*get package power through msr */
static float get_power()
{
    FILE *fp;
    float current_power;
    system("sudo /nfs/powPerfController/RaplPowerMon > power.txt");
    fp= fopen("power.txt","r");
    if (fp==NULL) handle_error("ERROR:opening file failed");
    fscanf(fp,"%f",&current_power);
    fclose(fp);
    return current_power;
}




static void handle_error(const char *msg)
{
    perror(msg);
    exit(EXIT_FAILURE);
}

