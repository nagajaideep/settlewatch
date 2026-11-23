package com.settlewatch.service;

import java.time.DayOfWeek;
import java.time.LocalDate;

/** Weekend-aware date arithmetic (holiday calendars are out of scope). */
public final class BusinessDays {

    private BusinessDays() {
    }

    public static LocalDate add(LocalDate from, int days) {
        LocalDate d = from;
        int added = 0;
        while (added < days) {
            d = d.plusDays(1);
            if (isBusinessDay(d)) {
                added++;
            }
        }
        return d;
    }

    public static boolean isBusinessDay(LocalDate d) {
        DayOfWeek dow = d.getDayOfWeek();
        return dow != DayOfWeek.SATURDAY && dow != DayOfWeek.SUNDAY;
    }
}
