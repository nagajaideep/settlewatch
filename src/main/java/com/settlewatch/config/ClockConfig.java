package com.settlewatch.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;
import java.util.Random;
import java.util.random.RandomGenerator;

@Configuration
public class ClockConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    RandomGenerator settlementRandom() {
        return new Random(); // thread-safe; the default L32X64MixRandom needs jdk.random, absent from slim JREs
    }
}
