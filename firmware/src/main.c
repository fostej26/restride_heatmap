/*
 * ReStride 16-sensor insole scanner.
 * 3 address GPIOs -> NAND decoder -> 74HC4066 switches; two banks of 8 onto AIN4 / AIN5.
 * Streams ASCII frames on the console UART (DK VCOM):
 *   I,restride-heatmap,<fw>,channels=16,rref=<ohms>,map=2-3-...      (boot, repeated every 5 s)
 *   F,<seq>,<t_ms>,<vdd_mv>,<r0>,...,<r15>                           (every frame)
 */
#include <zephyr/kernel.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/printk.h>

#include "channel_map.h"

#define ZU DT_PATH(zephyr_user)

static const struct adc_dt_spec adc_ch[3] = {
	ADC_DT_SPEC_GET_BY_IDX(ZU, 0), /* BUS_A */
	ADC_DT_SPEC_GET_BY_IDX(ZU, 1), /* BUS_B */
	ADC_DT_SPEC_GET_BY_IDX(ZU, 2), /* VDD */
};

static const struct gpio_dt_spec addr_pin[3] = {
	GPIO_DT_SPEC_GET_BY_IDX(ZU, mux_addr_gpios, 0), /* A0 */
	GPIO_DT_SPEC_GET_BY_IDX(ZU, mux_addr_gpios, 1), /* A1 */
	GPIO_DT_SPEC_GET_BY_IDX(ZU, mux_addr_gpios, 2), /* A2 */
};

/* 0.9 V reference / gain 1/4 = 3.6 V over 4096 counts. Must match host/frames.py. */
#define ADC_FULL_MV 3600
#define ADC_COUNTS 4096

static void mux_select(unsigned int k)
{
	for (int b = 0; b < 3; b++) {
		gpio_pin_set_dt(&addr_pin[b], (k >> b) & 1);
	}
}

static int mux_init(void)
{
	for (int b = 0; b < 3; b++) {
		if (!gpio_is_ready_dt(&addr_pin[b]) ||
		    gpio_pin_configure_dt(&addr_pin[b], GPIO_OUTPUT_INACTIVE) < 0) {
			return -ENODEV;
		}
	}
	return 0;
}

static int adc_init(void)
{
	for (int i = 0; i < 3; i++) {
		if (!adc_is_ready_dt(&adc_ch[i]) || adc_channel_setup_dt(&adc_ch[i]) < 0) {
			return -ENODEV;
		}
	}
	return 0;
}

static int16_t clamp0(int16_t v)
{
	return v < 0 ? 0 : v; /* single-ended noise near 0 V can read slightly negative */
}

/* Both buses in one sequence; samples come back in ascending channel-id order. */
static int read_buses(int16_t *a, int16_t *b)
{
	int16_t buf[2];
	bool a_first = adc_ch[0].channel_id < adc_ch[1].channel_id;
	struct adc_sequence seq = {
		.channels = BIT(adc_ch[0].channel_id) | BIT(adc_ch[1].channel_id),
		.buffer = buf,
		.buffer_size = sizeof(buf),
		.resolution = adc_ch[0].resolution,
		.oversampling = CONFIG_RESTRIDE_OVERSAMPLING,
	};
	int err = adc_read_dt(&adc_ch[0], &seq);

	if (err) {
		return err;
	}
	*a = clamp0(buf[a_first ? 0 : 1]);
	*b = clamp0(buf[a_first ? 1 : 0]);
	return 0;
}

static int read_vdd_mv(void)
{
	int16_t v = 0;
	struct adc_sequence seq = {
		.channels = BIT(adc_ch[2].channel_id),
		.buffer = &v,
		.buffer_size = sizeof(v),
		.resolution = adc_ch[2].resolution,
	};

	if (adc_read_dt(&adc_ch[2], &seq)) {
		return -1;
	}
	return (clamp0(v) * ADC_FULL_MV) / ADC_COUNTS;
}

static void print_info(void)
{
	printk("I,restride-heatmap,%s,channels=%d,rref=%d,map=", CONFIG_RESTRIDE_FW_VERSION, N_CH,
	       CONFIG_RESTRIDE_RREF_OHMS);
	for (int i = 0; i < N_CH; i++) {
		printk("%d%s", CH_TO_FPC[i], i < N_CH - 1 ? "-" : "");
	}
	printk("\n");
}

int main(void)
{
	if (mux_init() || adc_init()) {
		printk("E,init failed\n");
		return 0;
	}

#ifdef CONFIG_RESTRIDE_MUX_SELFTEST
	for (unsigned int k = 0;; k = (k + 1) % N_ROWS) {
		mux_select(k);
		printk("selftest k=%u (A2A1A0=%u%u%u): SEL%u should be the only high line\n", k,
		       (k >> 2) & 1, (k >> 1) & 1, k & 1, k);
		k_sleep(K_SECONDS(2));
	}
#else
	uint32_t seq = 0;
	int64_t next = k_uptime_get();
	int64_t next_info = next;

	print_info();
	while (1) {
		int16_t raw[N_CH];
		int vdd = read_vdd_mv();

		for (unsigned int k = 0; k < N_ROWS; k++) {
			mux_select(k);
			k_busy_wait(CONFIG_RESTRIDE_MUX_SETTLE_US);
			if (read_buses(&raw[k], &raw[k + N_ROWS])) {
				raw[k] = raw[k + N_ROWS] = 0;
			}
		}

		printk("F,%u,%u,%d", seq++, (uint32_t)k_uptime_get(), vdd);
		for (int i = 0; i < N_CH; i++) {
			printk(",%d", raw[i]);
		}
		printk("\n");

		if (k_uptime_get() >= next_info + 5000) {
			next_info = k_uptime_get();
			print_info(); /* repeated so a host can find the port after boot */
		}
		next += CONFIG_RESTRIDE_FRAME_PERIOD_MS;
		k_sleep(K_TIMEOUT_ABS_MS(next));
	}
#endif
	return 0;
}
