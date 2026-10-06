/* Minimal host test framework: CHECK / CHECK_EQ / CHECK_STR, RUN(test), summary in test_main. */
#ifndef UNITY_LITE_H
#define UNITY_LITE_H

#include <stdio.h>
#include <string.h>

static int ul_fail, ul_checks;

#define CHECK(c)                                                                     \
    do {                                                                             \
        ul_checks++;                                                                 \
        if (!(c)) {                                                                  \
            ul_fail++;                                                               \
            printf("%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #c);             \
        }                                                                            \
    } while (0)

#define CHECK_EQ(a, b)                                                               \
    do {                                                                             \
        long long ul_a = (long long)(a), ul_b = (long long)(b);                      \
        ul_checks++;                                                                 \
        if (ul_a != ul_b) {                                                          \
            ul_fail++;                                                               \
            printf("%s:%d: %s = %lld, expected %lld\n", __FILE__, __LINE__, #a, ul_a, ul_b); \
        }                                                                            \
    } while (0)

#define CHECK_STR(a, b)                                                              \
    do {                                                                             \
        ul_checks++;                                                                 \
        if (strcmp((a), (b)) != 0) {                                                 \
            ul_fail++;                                                               \
            printf("%s:%d: \"%s\" != \"%s\"\n", __FILE__, __LINE__, (a), (b));       \
        }                                                                            \
    } while (0)

#define RUN(t)                                                                       \
    do {                                                                             \
        int ul_before = ul_fail;                                                     \
        t();                                                                         \
        printf("%-40s %s\n", #t, ul_fail == ul_before ? "ok" : "FAIL");              \
    } while (0)

#define TEST_RESULT() (printf("%d checks, %d failed\n", ul_checks, ul_fail), ul_fail ? 1 : 0)

#endif
