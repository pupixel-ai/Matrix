#!/usr/bin/env python3
"""Run the production monitor decision method with deterministic host-side inputs."""

import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Matrix/WCCrashBlockMonitor/CrashBlockPlugin/Main/BlockMonitor/WCBlockMonitorMgr.mm"

HARNESS = r"""
#import <Foundation/Foundation.h>
#include <assert.h>
#include <sys/time.h>
#include <stdint.h>
#include <initializer_list>
#define __timercmp(a, b, CMP) (((a)->tv_sec == (b)->tv_sec) ? ((a)->tv_usec CMP (b)->tv_usec) : ((a)->tv_sec CMP (b)->tv_sec))
#undef TARGET_OS_OSX
#define TARGET_OS_OSX 0
#define MatrixInfo(...)
#define MatrixDebug(...)
#define BM_SAFE_CALL_SELECTOR_NO_RETURN(...) do {} while (0);
#define PRINT_MEMORY_USE_INTERVAL 5000000
#define PRINT_CPU_FREQUENCY_INTERVAL 10000000
#define UIApplicationStateBackground 2

typedef enum { EDumpType_Unlag, EDumpType_MainThreadBlock,
    EDumpType_BackgroundMainThreadBlock, EDumpType_CPUBlock } EDumpType;
static BOOL g_bRun;
static struct timeval g_tvRun, g_tvSuspend, g_lastCheckTime;
static unsigned int g_RunLoopTimeOut = 2000000, g_CheckPeriodTime = 1000000;
static float g_CPUUsagePercent = 80;
static BOOL g_bBackgroundLaunch, g_bLaunchOver;
static uint64_t matrix_footprintMemory(void) { return 0; }
static uint64_t matrix_availableMemory(void) { return 0; }

@interface FixtureCollector : NSObject
@property int samples;
@property int conclusions;
- (float)getCPUUsageAndPowerConsumeStack;
- (void)makeConclusion;
- (BOOL)isCPUHighBlock;
@end
@implementation FixtureCollector
- (float)getCPUUsageAndPowerConsumeStack { self.samples += 1; return 100; }
- (void)makeConclusion { self.conclusions += 1; }
- (BOOL)isCPUHighBlock { return YES; }
@end

@interface FixtureCPUHandler : NSObject
@property int windows;
- (BOOL)cultivateCpuUsage:(float)usage periodTime:(float)period;
@end
@implementation FixtureCPUHandler
- (BOOL)cultivateCpuUsage:(float)usage periodTime:(float)period {
    assert(usage == 100 && period > 0);
    self.windows += 1;
    return YES;
}
@end

@interface FixtureConfiguration : NSObject
- (BOOL)getShouldPrintCPUUsage;
- (BOOL)getShouldGetCPUHighLog;
- (unsigned int)getMemoryWarningThresholdInMB;
@end
@implementation FixtureConfiguration
- (BOOL)getShouldPrintCPUUsage { return NO; }
- (BOOL)getShouldGetCPUHighLog { return YES; }
- (unsigned int)getMemoryWarningThresholdInMB { return 400; }
@end

@interface MatrixDeviceInfo : NSObject
+ (float)appCpuUsage;
+ (float)cpuUsage;
+ (unsigned int)cpuCount;
@end
@implementation MatrixDeviceInfo
+ (float)appCpuUsage { return 100; }
+ (float)cpuUsage { return 100; }
+ (unsigned int)cpuCount { return 1; }
@end

@interface WCBlockMonitorMgr : NSObject {
@public
    uint64_t m_blockDiffTime;
    int m_currentState;
    BOOL m_bTrackCPU;
    unsigned int m_printMemoryTickTok, m_printCPUFrequencyTickTok;
    FixtureCollector *m_powerConsumeStackCollector;
    FixtureCPUHandler *m_cpuHandler;
    FixtureConfiguration *_monitorConfigHandler;
}
+ (unsigned long long)diffTime:(struct timeval *)start endTime:(struct timeval *)end;
- (EDumpType)check;
@end
@implementation WCBlockMonitorMgr
+ (unsigned long long)diffTime:(struct timeval *)start endTime:(struct timeval *)end {
    return (end->tv_sec - start->tv_sec) * 1000000ULL + end->tv_usec - start->tv_usec;
}
__PRODUCTION_CHECK__
@end

static WCBlockMonitorMgr *fixture(BOOL hang, BOOL background, BOOL suspended) {
    struct timeval now;
    gettimeofday(&now, NULL);
    g_bRun = hang;
    g_tvRun = now;
    g_tvRun.tv_sec -= 3;
    g_tvRun.tv_usec = 1;
    g_tvSuspend = g_tvRun;
    if (suspended) { g_tvSuspend.tv_sec += 1; }
    g_lastCheckTime = now;
    g_lastCheckTime.tv_sec -= 1;
    WCBlockMonitorMgr *monitor = [WCBlockMonitorMgr new];
    monitor->m_currentState = background ? UIApplicationStateBackground : 0;
    monitor->m_bTrackCPU = YES;
    monitor->m_printMemoryTickTok = PRINT_MEMORY_USE_INTERVAL;
    monitor->m_printCPUFrequencyTickTok = PRINT_CPU_FREQUENCY_INTERVAL;
    monitor->m_powerConsumeStackCollector = [FixtureCollector new];
    monitor->m_cpuHandler = [FixtureCPUHandler new];
    monitor->_monitorConfigHandler = [FixtureConfiguration new];
    return monitor;
}

int main(void) {
    @autoreleasepool {
        for (BOOL background : {NO, YES}) {
            WCBlockMonitorMgr *monitor = fixture(YES, background, NO);
            EDumpType expected = background ? EDumpType_BackgroundMainThreadBlock : EDumpType_MainThreadBlock;
            assert([monitor check] == expected);
            assert(monitor->m_powerConsumeStackCollector.samples == 1);
            assert(monitor->m_cpuHandler.windows == 1);
            assert(monitor->m_powerConsumeStackCollector.conclusions == 1);
        }
        WCBlockMonitorMgr *cpu = fixture(NO, NO, NO);
        assert([cpu check] == EDumpType_CPUBlock);
        assert(cpu->m_powerConsumeStackCollector.samples == 1);
        WCBlockMonitorMgr *suspended = fixture(YES, NO, YES);
        assert([suspended check] == EDumpType_Unlag);
        assert(suspended->m_powerConsumeStackCollector.samples == 0);
        assert(suspended->m_cpuHandler.windows == 0);
    }
    puts("CPU sampling/window continues during foreground/background hangs; classification and suspend guard preserved");
}
"""


def main():
    source = SOURCE.read_text()
    start = source.index("- (EDumpType)check {")
    end = source.index("\n- (EFilterType)needFilter", start)
    method = source[start:end]
    with tempfile.TemporaryDirectory(prefix="matrix-cpu-regression-") as directory:
        path = pathlib.Path(directory)
        harness = path / "check.mm"
        harness.write_text(HARNESS.replace("__PRODUCTION_CHECK__", method))
        executable = path / "check"
        subprocess.run([
            "xcrun", "clang++", "-std=c++11", "-fobjc-arc", "-framework", "Foundation",
            str(harness), "-o", str(executable),
        ], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
