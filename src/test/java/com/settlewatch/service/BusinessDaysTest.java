package com.settlewatch.service;

import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;

class BusinessDaysTest {

    @Test
    void fridayPlusOneIsMonday() {
        assertThat(BusinessDays.add(LocalDate.of(2026, 11, 20), 1)).isEqualTo(LocalDate.of(2026, 11, 23));
    }

    @Test
    void midweekPlusTwo() {
        assertThat(BusinessDays.add(LocalDate.of(2026, 11, 24), 2)).isEqualTo(LocalDate.of(2026, 11, 26));
    }

    @Test
    void zeroDaysIsSameDay() {
        assertThat(BusinessDays.add(LocalDate.of(2026, 11, 21), 0)).isEqualTo(LocalDate.of(2026, 11, 21));
    }
}
