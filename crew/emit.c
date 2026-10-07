/* crew-emit <journal> <harness>: observation hook writer.
 *
 * Reads one hook payload on stdin and appends a single metadata-only line to
 * the local journal. It copies a fixed set of small top-level fields and
 * nothing else: no prompts, tool inputs or responses reach the journal. It
 * never touches the network, prints the neutral hook result and exits 0
 * whatever happens, so a failed write only becomes an observation error.
 */
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <time.h>
#include <unistd.h>

enum { KEY_MAX = 40, VAL_MAX = 1024, OUT_MAX = 16384, LOCK_WAIT_NS = 5000000 };

static const char *STR_KEYS[] = {
    "hook_event_name", "session_id", "transcript_path", "cwd", "agent_id",
    "agent_transcript_path", "agent_type", "turn_id", "prompt_id",
    "notification_type", "source", "reason", "tool_name", "tool_use_id", NULL};
static const char *BOOL_KEYS[] = {"stop_hook_active", NULL};

static char out[OUT_MAX];
static size_t out_len;

static int listed(const char **keys, const char *key) {
    for (; *keys; keys++)
        if (strcmp(*keys, key) == 0) return 1;
    return 0;
}

static void field(const char *key, const char *raw, size_t raw_len, int quote) {
    size_t need = strlen(key) + raw_len + 8;
    if (out_len + need >= OUT_MAX - 4) return; /* keep room for the closing */
    out_len += (size_t)snprintf(out + out_len, OUT_MAX - out_len, ",\"%s\":%s", key,
                                quote ? "\"" : "");
    memcpy(out + out_len, raw, raw_len);
    out_len += raw_len;
    if (quote) out[out_len++] = '"';
}

/* Streaming scan for top-level members; nested values are skipped unparsed. */
static void scan(void) {
    char buf[65536], key[KEY_MAX] = "", tok[VAL_MAX + 1];
    size_t tok_len = 0;
    int depth = 0, in_str = 0, esc = 0, expect_key = 0, is_value = 0, tok_over = 0;
    ssize_t n;
    while ((n = read(STDIN_FILENO, buf, sizeof buf)) > 0) {
        for (ssize_t i = 0; i < n; i++) {
            char c = buf[i];
            if (in_str) {
                if (!esc && c == '"') {
                    in_str = 0;
                    if (depth != 1) continue;
                    if (expect_key) {
                        expect_key = 0;
                        key[0] = 0;
                        if (!tok_over && tok_len < KEY_MAX) {
                            memcpy(key, tok, tok_len);
                            key[tok_len] = 0;
                        }
                    } else if (is_value) {
                        is_value = 0;
                        if (!tok_over && listed(STR_KEYS, key)) field(key, tok, tok_len, 1);
                    }
                    continue;
                }
                esc = !esc && c == '\\';
                if ((unsigned char)c < 0x20) c = ' '; /* a raw newline would split the record */
                if (depth == 1) {
                    if (tok_len < VAL_MAX) tok[tok_len++] = c;
                    else tok_over = 1;
                }
            } else if (c == '"') {
                in_str = 1, esc = 0, tok_len = 0, tok_over = 0;
            } else if (c == '{' || c == '[') {
                if (++depth == 1) expect_key = 1;
                else is_value = 0;
            } else if (c == '}' || c == ']') {
                depth--;
            } else if (depth == 1 && c == ':') {
                is_value = 1;
            } else if (depth == 1 && c == ',') {
                expect_key = 1, is_value = 0;
            } else if (depth == 1 && is_value && (c == 't' || c == 'f')) {
                is_value = 0;
                if (listed(BOOL_KEYS, key)) field(key, c == 't' ? "true" : "false", c == 't' ? 4 : 5, 0);
            }
        }
    }
}

static int append(const char *path, const char *data, size_t len, int wait_lock) {
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0600), ok = 0;
    if (fd < 0) return 0;
    struct timespec begin, now, pause = {0, 100000};
    clock_gettime(CLOCK_MONOTONIC, &begin);
    int locked = !wait_lock;
    while (!locked) {
        /* Shared: appenders never wait on each other, only on a truncation. */
        if (flock(fd, LOCK_SH | LOCK_NB) == 0) { locked = 1; break; }
        nanosleep(&pause, NULL);
        clock_gettime(CLOCK_MONOTONIC, &now);
        if ((now.tv_sec - begin.tv_sec) * 1000000000LL + now.tv_nsec - begin.tv_nsec >= LOCK_WAIT_NS)
            break;
    }
    if (locked) ok = write(fd, data, len) == (ssize_t)len;
    close(fd); /* releases the lock */
    return ok;
}

int main(int argc, char **argv) {
    if (argc == 3 && strspn(argv[2], "abcdefghijklmnopqrstuvwxyz") == strlen(argv[2]) &&
        strlen(argv[2]) < 16) {
        struct timespec now;
        clock_gettime(CLOCK_REALTIME, &now);
        long long ns = (long long)now.tv_sec * 1000000000LL + now.tv_nsec;
        out_len = (size_t)snprintf(out, OUT_MAX, "{\"ts_ns\":%lld,\"harness\":\"%s\"", ns, argv[2]);
        scan();
        out[out_len++] = '}';
        out[out_len++] = '\n';
        if (!append(argv[1], out, out_len, 1)) {
            /* Observation error: record it beside the journal, unlocked. */
            char path[4096], line[128];
            int len = snprintf(line, sizeof line, "{\"ts_ns\":%lld,\"harness\":\"%s\"}\n", ns, argv[2]);
            if (snprintf(path, sizeof path, "%s.errors", argv[1]) < (int)sizeof path)
                append(path, line, (size_t)len, 0);
        }
    }
    puts("{}");
    return 0;
}
