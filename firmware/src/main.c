#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/sys/printk.h>

#define FW_VERSION "1.0.0"

/* Sensors */
static const struct device *const si7021   = DEVICE_DT_GET(DT_NODELABEL(si7021));
static const struct device *const veml6035 = DEVICE_DT_GET(DT_NODELABEL(veml6035));
static const struct device *const si7210   = DEVICE_DT_GET(DT_NODELABEL(si7210));

/*
 * BLE manufacturer data (company id: 0xFFFF)
 * Payload after company ID (8 bytes):
 *   [0–1]  int16 LE  temperature (centi-°C)
 *   [2]    uint8     humidity (%RH)
 *   [3–4]  uint16 LE ambient light (lux)
 *   [5–6]  int16 LE  magnetic field (µT)
 *   [7]    uint8     sensor flags (bit0=temp/hum, bit1=lux, bit2=mag)
 */
static uint8_t mfr_data[] = {
    0xFF, 0xFF,   /* company id */
    0x00, 0x00,   /* temp */
    0x00,         /* hum */
    0x00, 0x00,   /* lux */
    0x00, 0x00,   /* mag */
    0x00,         /* flags */
};

static struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_NO_BREDR | BT_LE_AD_GENERAL),
    BT_DATA(BT_DATA_NAME_COMPLETE, "xG27-Sensor", 11),
    BT_DATA(BT_DATA_MANUFACTURER_DATA, mfr_data, sizeof(mfr_data)),
};

static bool ble_ready;

static void bt_ready_cb(int err)
{
    if (err) {
        printk("BLE error: %d\n", err);
        return;
    }
    err = bt_le_adv_start(BT_LE_ADV_NCONN, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err == 0) {
        ble_ready = true;
        printk("BLE advertising: xG27-Sensor\n");
    }
}

static void update_ble(int16_t temp_cdeg, uint8_t hum,
                       uint16_t lux, int16_t mag_ut, uint8_t flags)
{
    if (!ble_ready) {
        return;
    }
    mfr_data[2] = (uint8_t)(temp_cdeg & 0xFF);
    mfr_data[3] = (uint8_t)(temp_cdeg >> 8);
    mfr_data[4] = hum;
    mfr_data[5] = (uint8_t)(lux & 0xFF);
    mfr_data[6] = (uint8_t)(lux >> 8);
    mfr_data[7] = (uint8_t)(mag_ut & 0xFF);
    mfr_data[8] = (uint8_t)(mag_ut >> 8);
    mfr_data[9] = flags;
    bt_le_adv_update_data(ad, ARRAY_SIZE(ad), NULL, 0);
}

int main(void)
{
    k_msleep(500);

    /* Hardware watchdog: reset board if main loop stalls > 5 s */
    static int wdt_chan = -1;
#if DT_NODE_HAS_STATUS(DT_NODELABEL(wdog0), okay)
    {
        const struct device *wdt = DEVICE_DT_GET(DT_NODELABEL(wdog0));
        if (device_is_ready(wdt)) {
            struct wdt_timeout_cfg cfg = {
                .window  = {.min = 0U, .max = 5000U},
                .callback = NULL,
                .flags   = WDT_FLAG_RESET_SOC,
            };
            wdt_chan = wdt_install_timeout(wdt, &cfg);
            wdt_setup(wdt, WDT_OPT_PAUSE_HALTED_BY_DBG);
            printk("Watchdog armed (5 s)\n");
        }
    }
#endif

    bt_enable(bt_ready_cb);

    while (1) {
        struct sensor_value temp, hum, light, mag;
        int16_t  temp_cdeg = 0;
        uint8_t  hum_pct   = 0;
        uint16_t lux       = 0;
        int16_t  mag_ut    = 0;
        uint8_t  flags     = 0;

        if (device_is_ready(si7021) &&
            sensor_sample_fetch(si7021) == 0) {
            sensor_channel_get(si7021, SENSOR_CHAN_AMBIENT_TEMP, &temp);
            sensor_channel_get(si7021, SENSOR_CHAN_HUMIDITY, &hum);
            temp_cdeg = (int16_t)(temp.val1 * 100 +
                        (temp.val2 < 0 ? -(-temp.val2 / 10000)
                                       :   temp.val2 / 10000));
            hum_pct = (uint8_t)hum.val1;
            flags |= 1;
        }

        if (device_is_ready(veml6035) &&
            sensor_sample_fetch(veml6035) == 0) {
            sensor_channel_get(veml6035, SENSOR_CHAN_LIGHT, &light);
            lux = (uint16_t)light.val1;
            flags |= 2;
        }

        if (device_is_ready(si7210) &&
            sensor_sample_fetch(si7210) == 0) {
            sensor_channel_get(si7210, SENSOR_CHAN_MAGN_Z, &mag);
            /* Driver returns Gauss; 1 G = 100 µT.
             * Earth field (~0.44 G) lives entirely in val2, so include it:
             *   µT = val1 * 100 + val2 / 10000  */
            mag_ut = (int16_t)(mag.val1 * 100 + mag.val2 / 10000);
            flags |= 4;
        }

        update_ble(temp_cdeg, hum_pct, lux, mag_ut, flags);

        printk("{\"t\":%d.%02d,\"h\":%d,\"l\":%d,\"m\":%d,\"f\":%d}\n",
               temp_cdeg / 100, abs(temp_cdeg % 100),
               hum_pct, lux, mag_ut, flags);

        if (wdt_chan >= 0) {
            /* Defined at compile time only when wdog0 exists */
#if DT_NODE_HAS_STATUS(DT_NODELABEL(wdog0), okay)
            const struct device *wdt = DEVICE_DT_GET(DT_NODELABEL(wdog0));
            wdt_feed(wdt, wdt_chan);
#endif
        }

        k_msleep(1000);
    }

    return 0;
}
