/*
  A small glue code for Intel RAPL power capping

  This requires the msr-safe driver to be installed and configured
  correctly

  Kaz Yoshii <kazutomo@mcs.anl.gov>
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <regex.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <math.h>

#define MSRNAME "msr_safe"

#define MSR_RAPL_POWER_UNIT (0x00000606)
#define MSR_PKG_POWER_LIMIT (0x00000610)

int parse_cpuinfo_pkg_model(int *cores, int ncores,int *model);

/*
  Extract (h-l+1) bits from val and return l-bit shifted value
*/
inline uint64_t extractbits(uint64_t val, int l, int h )
{
  int w= h - l+ 1;
  uint64_t m;
  if(w<1) return 0;

  val = val >> l;
  m = (1UL<<w)-1;
  val = val & m;

  return val;
}

/*
  Insert newval into (h-l+1) bits of val and return updated val
*/
inline uint64_t insertbits(uint64_t val, int l, int h,uint64_t newval )
{
  int w= h - l+ 1;
  uint64_t m;
  if(w<1) return 0;

  m = (1UL<<w)-1;
  newval = newval & m;

  m = (1UL<<(h+1))-1 - ((1UL<<l)-1);
  m = ~m;

  val = (val&m) | (newval<<l);

  return val;
}


static int _open_msr(int coreid)
{
  char fn[1024];
  int fd;

  snprintf(fn,sizeof(fn),"/dev/cpu/%d/" MSRNAME, coreid);
  fd = open(fn, O_RDWR);
  if( fd<0 ) {
    printf("\n");
    printf("Failed to open %s. Is the msr safe driver installed? If so, check the permission.\n", fn);
    printf("\n");
    return -1;
  }
  return fd;
}



static uint64_t _read_msr(int fd, int offset) 
{
  uint64_t data;

  if( pread(fd, &data, 8, offset) != 8 ) {
	  printf("Warning: pread at 0x%x\n", offset);
	  return -1;
  }
  return data;
}

static uint64_t _write_msr(int fd, int offset, uint64_t data) 
{
  if( pwrite(fd, &data, 8, offset) != 8 ) {
    perror("pwrite");
    return -1;
  }
  return data;
}

#define MAX_RAPL_PKG (16)   /* # of sockets */

uint64_t set_power_limit(int pkgid, double watt)
{
  uint64_t val;
  double power_units;
  int npkg;
  int coreid[MAX_RAPL_PKG]; /* codeid for each pkg */
  int model;
  int fd;
  uint64_t  pkg_power_limit;

  npkg = parse_cpuinfo_pkg_model(coreid, MAX_RAPL_PKG, &model );
  if (pkgid >= npkg) return -1;
  if (pkgid < 0) return -1;

  fd = _open_msr(coreid[pkgid]);
  val = _read_msr(fd ,MSR_RAPL_POWER_UNIT);
  power_units  = pow(0.5,(double)( val     &0xf ));

  pkg_power_limit = _read_msr(fd, MSR_PKG_POWER_LIMIT);

  val = watt/power_units;
  _write_msr(fd, MSR_PKG_POWER_LIMIT, insertbits(pkg_power_limit, 0, 14, val));
  close(fd);

  return val;
}


int parse_cpuinfo_pkg_model(int *cores, int ncores,int *model)
{
  FILE* fp;
  char buf[128];
  regex_t r1, r2, r3;
  regmatch_t pm[3];
  char *s1 = "processor[^[:digit:]]+([[:digit:]]+)";
  char *s2 = "physical id[^[:digit:]]+([[:digit:]]+)";
  char *s3 = "model[[:blank:]]+:[[:blank:]]+([[:digit:]]+)";
  int i, rc;
  int coreid=-1, pkgid=-1;
  char tmpbuf[10];
  int tmplen;
  int pkgid_max=-1;

  *model = 0;

  for(i=0;i<ncores;i++)  cores[i] = -1;


  rc = regcomp(&r1, s1, REG_EXTENDED);
  if( rc ) {
    fprintf(stderr, "failed to compile %s\n",s1);   exit(1);
  }
  rc = regcomp(&r2, s2, REG_EXTENDED);
  if( rc ) {
    fprintf(stderr, "failed to compile %s\n",s2);   exit(1);
  }
  rc = regcomp(&r3, s3, REG_EXTENDED);
  if( rc ) {
    fprintf(stderr, "failed to compile %s\n",s3);   exit(1);
  }


  fp = fopen( "/proc/cpuinfo", "r" );

  while( fgets(buf, sizeof(buf), fp ) != (char*)0 ) {

    rc = regexec(&r1, buf, 3,  pm, 0);
    if( rc == 0 ) {
      if( pm[1].rm_so == -1 ) {
	printf("failed to match: %s\n", s1);
	exit(1);
      }
      tmplen = pm[1].rm_eo-pm[1].rm_so+1;
      if(tmplen>5) {
	printf("processor id is too long %s:\n", buf);
	exit(1);
      }
      strncpy(tmpbuf,buf+pm[1].rm_so, tmplen);
      tmpbuf[tmplen] = 0;
      coreid = atoi(tmpbuf);
    }

    rc = regexec(&r2, buf, 3,  pm, 0);
    if( rc == 0 ) {
      if( pm[1].rm_so == -1 ) {
	printf("failed to match: %s\n", s2);
	exit(1);
      }
      tmplen = pm[1].rm_eo-pm[1].rm_so+1;
      if(tmplen>2) {
	printf("physical id is too long: %s", buf);
	exit(1);
      }
      strncpy(tmpbuf,buf+pm[1].rm_so, tmplen);
      tmpbuf[tmplen] = 0;
      pkgid = atoi(tmpbuf);
      
      /* XXX: assume physical id is continuous .
	 "processor id" is parsed before "physical id".
	 Use the first appeared core id as pkgcore.
       */
      if(pkgid>=ncores) {
	printf("physical id is too big: %d\n",pkgid);
	exit(1);
      }
      if( cores[pkgid]==-1 ) {

	if( coreid==-1 ) {
	  printf("coreid is not parsed yet\n");
	  exit(1);
	}

	cores[pkgid] = coreid;
	if( pkgid> pkgid_max ) pkgid_max = pkgid;
      }
    }

    if( *model == 0 ) {
      rc = regexec(&r3, buf, 3,  pm, 0);
      if( rc == 0 ) {
	if( pm[1].rm_so == -1 ) {
	  printf("failed to match: %s\n", s2);
	  exit(1);
	}

	tmplen = pm[1].rm_eo-pm[1].rm_so+1;
	if(tmplen>4) {
	  printf("model is too long: %s", buf);
	  exit(1);
	}
	strncpy(tmpbuf,buf+pm[1].rm_so, tmplen);
	*model = atoi(tmpbuf);
      }
    }
  }
  fclose(fp);

  return pkgid_max+1;
}

int main()
{
	set_power_limit(1, 122.0);

	return 0;
}
