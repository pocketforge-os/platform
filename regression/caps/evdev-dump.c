/* regression/caps/evdev-dump.c — static-binary fallback for evdev-probe.py (SPIKE-0).
 *
 * For stock userlands with no usable python (the deployment hazard on the A133
 * CrossMix / BusyBox images). Emits the SAME JSON capture shape evdev-probe.py does,
 * so `pf caps probe-diff` consumes either transcript unchanged; --watch is the same
 * press-test substitute (decoded live events + a codes-seen JSON summary).
 *
 *   build (host):   aarch64-linux-gnu-gcc -static -O2 -o evdev-dump evdev-dump.c
 *   on device:      ./evdev-dump > /tmp/a133-probe.json
 *                   ./evdev-dump --watch /dev/input/event0 --seconds 60
 *
 * Code names are printed raw ("0x130") — name mapping happens host-side in
 * `pf caps probe-diff` / evdev-probe.py's tables; keeping this binary name-free
 * means it can never drift from the generated vocab. EXCEPTION: probe-diff matches
 * key/abs names, so the capture must carry the SAME names evdev-probe.py emits.
 * We therefore embed the generated tables via evdev-dump-codes.h (emitted by
 * gen_evdev_probe_codes.py --c-header; --check covers drift).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <linux/input.h>
#include <dirent.h>

#include "evdev-dump-codes.h"   /* BTN/KEY/ABS name tables, generated — do not edit */

#define EV_MAXBIT 0x2ff

static const char *ev_name(int e) {
    switch (e) {
    case 0x00: return "EV_SYN"; case 0x01: return "EV_KEY"; case 0x02: return "EV_REL";
    case 0x03: return "EV_ABS"; case 0x04: return "EV_MSC"; case 0x05: return "EV_SW";
    case 0x11: return "EV_LED"; case 0x15: return "EV_FF";
    default: return NULL;
    }
}

static const char *lookup(const struct code_name *tab, size_t n, int code) {
    for (size_t i = 0; i < n; i++)
        if (tab[i].code == code) return tab[i].name;
    return NULL;
}

static const char *key_name(int code, char *tmp, size_t tn) {
    const char *s = lookup(PF_BTN_TAB, PF_BTN_TAB_LEN, code);
    if (!s) s = lookup(PF_KEY_TAB, PF_KEY_TAB_LEN, code);
    if (s) return s;
    snprintf(tmp, tn, "0x%x", code);
    return tmp;
}

static const char *abs_name(int code, char *tmp, size_t tn) {
    const char *s = lookup(PF_ABS_TAB, PF_ABS_TAB_LEN, code);
    if (s) return s;
    snprintf(tmp, tn, "0x%x", code);
    return tmp;
}

static int test_bit(const unsigned char *buf, int bit) {
    return (buf[bit / 8] >> (bit % 8)) & 1;
}

/* JSON string escape for device names (quotes/backslash/control chars). */
static void json_str(const char *s) {
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
        else if (c < 0x20) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}

static int dump_node(const char *path, int first) {
    char tmp[16];
    int fd = open(path, O_RDONLY);
    if (!first) printf(",\n");
    printf("    {\n      \"path\": "); json_str(path);
    if (fd < 0) {
        printf(",\n      \"error\": "); json_str(strerror(errno));
        printf("\n    }");
        return 0;
    }
    char name[256] = "";
    if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0) name[0] = 0;
    printf(",\n      \"name\": "); json_str(name);
    struct input_id iid;
    if (ioctl(fd, EVIOCGID, &iid) == 0)
        printf(",\n      \"bustype\": %u,\n      \"vendor\": \"%04x\","
               "\n      \"product\": \"%04x\",\n      \"version\": \"%04x\"",
               iid.bustype, iid.vendor, iid.product, iid.version);
    unsigned char evbuf[4] = {0};
    ioctl(fd, EVIOCGBIT(0, sizeof(evbuf)), evbuf);
    printf(",\n      \"ev\": [");
    int firstev = 1, has_key = 0, has_abs = 0, has_ff = 0;
    for (int e = 0; e < 32; e++) {
        if (!test_bit(evbuf, e)) continue;
        if (e == EV_KEY) has_key = 1;
        if (e == EV_ABS) has_abs = 1;
        if (e == EV_FF)  has_ff = 1;
        const char *en = ev_name(e);
        printf("%s", firstev ? "" : ", ");
        if (en) json_str(en); else { char b[16]; snprintf(b, sizeof(b), "EV_0x%x", e); json_str(b); }
        firstev = 0;
    }
    printf("]");
    if (has_key) {
        unsigned char kb[(EV_MAXBIT / 8) + 1] = {0};
        ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(kb)), kb);
        printf(",\n      \"keys\": [");
        int firstk = 1;
        for (int c = 0; c <= EV_MAXBIT; c++) {
            if (!test_bit(kb, c)) continue;
            printf("%s", firstk ? "" : ", ");
            json_str(key_name(c, tmp, sizeof(tmp)));
            firstk = 0;
        }
        printf("]");
    }
    if (has_abs) {
        unsigned char ab[(0x3f / 8) + 1] = {0};
        ioctl(fd, EVIOCGBIT(EV_ABS, sizeof(ab)), ab);
        printf(",\n      \"abs\": {");
        int firsta = 1;
        for (int a = 0; a <= 0x3f; a++) {
            if (!test_bit(ab, a)) continue;
            struct input_absinfo ai;
            if (ioctl(fd, EVIOCGABS(a), &ai) < 0) continue;
            printf("%s\n        ", firsta ? "" : ",");
            json_str(abs_name(a, tmp, sizeof(tmp)));
            printf(": {\"min\": %d, \"max\": %d, \"fuzz\": %d, \"flat\": %d, \"resolution\": %d}",
                   ai.minimum, ai.maximum, ai.fuzz, ai.flat, ai.resolution);
            firsta = 0;
        }
        printf("\n      }");
    }
    if (has_ff) printf(",\n      \"ev_ff\": true");
    printf("\n    }");
    close(fd);
    return 0;
}

struct wnode {
    int fd;
    const char *path;
    char name[256];
    int last[0x40];       /* last printed ABS value per code */
    int have_last[0x40];
    int delta[0x40];
    unsigned char seen_key[(EV_MAXBIT / 8) + 1];
    unsigned char seen_abs[(0x3f / 8) + 1];
};

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int watch(char **paths, int n, double seconds) {
    char tmp[16];
    struct wnode w[64];
    int nn = 0;
    for (int i = 0; i < n && nn < 64; i++) {
        int fd = open(paths[i], O_RDONLY | O_NONBLOCK);
        if (fd < 0) { printf("# %s: %s\n", paths[i], strerror(errno)); continue; }
        struct wnode *x = &w[nn];
        memset(x, 0, sizeof(*x));
        x->fd = fd; x->path = paths[i];
        if (ioctl(fd, EVIOCGNAME(sizeof(x->name)), x->name) < 0) x->name[0] = 0;
        unsigned char ab[(0x3f / 8) + 1] = {0};
        ioctl(fd, EVIOCGBIT(EV_ABS, sizeof(ab)), ab);
        for (int a = 0; a <= 0x3f; a++) {
            struct input_absinfo ai;
            x->delta[a] = 1;
            if (test_bit(ab, a) && ioctl(fd, EVIOCGABS(a), &ai) == 0) {
                int d = (ai.maximum - ai.minimum) / 64;
                x->delta[a] = d > 1 ? d : 1;
            }
        }
        printf("# watching %s \"%s\"\n", x->path, x->name);
        nn++;
    }
    if (!nn) { printf("# watch: no readable nodes\n"); return 1; }
    fflush(stdout);
    double t0 = now_s(), deadline = t0 + seconds;
    while (now_s() < deadline) {
        fd_set rs; FD_ZERO(&rs);
        int maxfd = 0;
        for (int i = 0; i < nn; i++) { FD_SET(w[i].fd, &rs); if (w[i].fd > maxfd) maxfd = w[i].fd; }
        double left = deadline - now_s();
        struct timeval tv = { (time_t)(left < 1.0 ? left : 1.0),
                              (suseconds_t)((left < 1.0 ? left : 1.0) * 1e6) % 1000000 };
        if (select(maxfd + 1, &rs, NULL, NULL, &tv) <= 0) continue;
        for (int i = 0; i < nn; i++) {
            if (!FD_ISSET(w[i].fd, &rs)) continue;
            struct input_event ev[64];
            ssize_t r = read(w[i].fd, ev, sizeof(ev));
            if (r <= 0) continue;
            for (int k = 0; k < (int)(r / sizeof(struct input_event)); k++) {
                int t = ev[k].type, c = ev[k].code, v = ev[k].value;
                const char *nm;
                if (t == EV_KEY) {
                    if (c <= EV_MAXBIT) w[i].seen_key[c / 8] |= 1 << (c % 8);
                    nm = key_name(c, tmp, sizeof(tmp));
                } else if (t == EV_ABS) {
                    if (c > 0x3f) continue;
                    if (w[i].have_last[c] && abs(v - w[i].last[c]) < w[i].delta[c]) continue;
                    w[i].last[c] = v; w[i].have_last[c] = 1;
                    w[i].seen_abs[c / 8] |= 1 << (c % 8);
                    nm = abs_name(c, tmp, sizeof(tmp));
                } else continue;
                const char *base = strrchr(w[i].path, '/');
                printf("[%7.2fs] %s %s %s %d\n", now_s() - t0,
                       base ? base + 1 : w[i].path, ev_name(t), nm, v);
                fflush(stdout);
            }
        }
    }
    printf("{\"watch_summary\": {");
    for (int i = 0; i < nn; i++) {
        printf("%s", i ? ", " : "");
        json_str(w[i].path);
        printf(": {\"name\": "); json_str(w[i].name);
        printf(", \"codes_seen\": [");
        int firstc = 1;
        for (int c = 0; c <= EV_MAXBIT; c++)
            if (w[i].seen_key[c / 8] & (1 << (c % 8))) {
                printf("%s", firstc ? "" : ", ");
                json_str(key_name(c, tmp, sizeof(tmp)));
                firstc = 0;
            }
        for (int c = 0; c <= 0x3f; c++)
            if (w[i].seen_abs[c / 8] & (1 << (c % 8))) {
                printf("%s", firstc ? "" : ", ");
                json_str(abs_name(c, tmp, sizeof(tmp)));
                firstc = 0;
            }
        printf("]}");
        close(w[i].fd);
    }
    printf("}}\n");
    return 0;
}

static int cmp_str(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

int main(int argc, char **argv) {
    int do_watch = 0;
    double seconds = 120.0;
    char *paths[256];
    int np = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--watch")) do_watch = 1;
        else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) seconds = atof(argv[++i]);
        else if (np < 256) paths[np++] = argv[i];
    }
    static char found[256][280];
    if (!np) {
        DIR *d = opendir("/dev/input");
        struct dirent *de;
        if (d) {
            while ((de = readdir(d)) && np < 256)
                if (!strncmp(de->d_name, "event", 5)) {
                    snprintf(found[np], sizeof(found[np]), "/dev/input/%s", de->d_name);
                    paths[np] = found[np];
                    np++;
                }
            closedir(d);
        }
        qsort(paths, np, sizeof(char *), cmp_str);
    }
    if (do_watch) return watch(paths, np, seconds);
    printf("{\n  \"nodes\": [\n");
    for (int i = 0; i < np; i++) dump_node(paths[i], i == 0);
    printf("\n  ]\n}\n");
    return 0;
}
