
# the compiler: gcc for C program, define as g++ for C++
CC = gcc

# compiler flags:
CFLAGS  = -g -I/nfs/beacon_inst/include -I.
LDFLAGS = -lm -lbeacon -lpthread

# the build target executable:
TARGET = powPerfController
powMon = RaplPowerMon
beacon = beacon_nrm

RM = rm

all: $(powMon) $(TARGET)

$(powMon): $(powMon).c
	$(CC) -o $(powMon) $(powMon).c $(LDFLAGS)

$(TARGET): $(TARGET).c $(beacon).c  
	$(CC) $(CFLAGS) $(TARGET).c $(beacon).c -o $(TARGET) $(LDFLAGS)

clean:
	$(RM) -f $(TARGET) $(powMon)


