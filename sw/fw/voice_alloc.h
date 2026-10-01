/* Voice allocation (hardware independent, host-tested in sw/test/test_voice_alloc.c).
 * Policy (trs.md 4.2): the same note reuses its voice; otherwise a free voice (envelope idle);
 * otherwise steal the releasing voice with the lowest level; otherwise the oldest voice. */
#ifndef VOICE_ALLOC_H
#define VOICE_ALLOC_H

#include <stdint.h>

#define VA_MAX_VOICES 64
#define VA_NO_NOTE    0xFF

struct va_voice {
    uint8_t note;      /* VA_NO_NOTE when never used */
    uint8_t held;      /* key down */
    uint8_t sustained; /* key up while the sustain pedal is down */
    uint32_t age;      /* note-on stamp */
};

struct va_hw {         /* envelope state of voice v from the hardware */
    int (*idle)(void *ctx, int v);
    uint32_t (*level)(void *ctx, int v);
    void *ctx;
};

struct voice_alloc {
    int n;
    uint8_t sustain;
    uint32_t clock;
    struct va_hw hw;
    struct va_voice v[VA_MAX_VOICES];
};

void va_init(struct voice_alloc *a, int n, struct va_hw hw);
/* returns the voice for the note; *retrig = 1 if that voice is currently gated (restart envelopes) */
int va_note_on(struct voice_alloc *a, uint8_t note, int *retrig);
/* returns the voice to gate off, or -1 (unknown note, or held by the sustain pedal) */
int va_note_off(struct voice_alloc *a, uint8_t note);
/* pedal: on release returns a bit mask of voices to gate off (in *mask, 64 bits as two words) */
void va_sustain(struct voice_alloc *a, int on, uint32_t mask[2]);
/* all notes off: mask of voices that were gated */
void va_all_off(struct voice_alloc *a, uint32_t mask[2]);
int va_gated(const struct voice_alloc *a, int v);

#endif
