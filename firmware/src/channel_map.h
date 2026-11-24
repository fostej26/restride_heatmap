/* Channel index -> FPC pin. Single source of truth for the firmware; the host reads the same
 * mapping from the `map=` field of the I line (and host/layout.json). */
#ifndef CHANNEL_MAP_H_
#define CHANNEL_MAP_H_

#define N_CH 16
#define N_ROWS 8 /* 3-bit address -> 8 rows, 2 banks */

/* ch0..7 = bank A (BUS_A, AIN4), ch8..15 = bank B (BUS_B, AIN5); row k gives ch k and ch k+8 */
static const unsigned char CH_TO_FPC[N_CH] = {
	2, 3, 4, 5, 7, 8, 9, 10,
	12, 13, 15, 16, 17, 18, 19, 20,
};

#endif
