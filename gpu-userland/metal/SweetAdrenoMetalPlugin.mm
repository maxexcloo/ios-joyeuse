// SPDX-License-Identifier: MIT
// iOS16 discovery entry for the native Metal frontend. No target-specific
// QuartzCore addresses, memory writes, smoke tests or fabricated Metal device.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <limits.h>
#include <string.h>
#include <unistd.h>
#include "NativeBridgeMetalFrontend.h"

@interface _MTLDevice : NSObject
@end
@interface SweetAdrenoMetalDevice : _MTLDevice
- (id)initWithAcceleratorPort:(unsigned)port;
@end
@implementation SweetAdrenoMetalDevice
- (id)initWithAcceleratorPort:(unsigned)port {
    self=[super init];
    if(!self || !port)return nil;
    // Initial deployment is the system compositor. Other processes retain
    // their existing rendering path until multiple contexts are implemented.
    if(![[NSProcessInfo processInfo].processName isEqualToString:@"backboardd"])return nil;
    Dl_info location={};
    if(!dladdr((const void *)&native_bridge_metal_open,&location) || !location.dli_fname)return nil;
    char loader[PATH_MAX]={};
    const char *slash=strrchr(location.dli_fname,'/');
    if(!slash)return nil;
    const size_t prefix=(size_t)(slash-location.dli_fname)+1;
    if(prefix+sizeof("libvulkan_freedreno.dylib")>sizeof loader)return nil;
    memcpy(loader,location.dli_fname,prefix);
    memcpy(loader+prefix,"libvulkan_freedreno.dylib",sizeof("libvulkan_freedreno.dylib"));
    // The runtime creates its device only if Turnip successfully opens the
    // real NativeAdreno userclient and supplies its actual hardware profile.
    NSArray *directories=NSSearchPathForDirectoriesInDomains(NSCachesDirectory,NSUserDomainMask,YES);
    NSString *cache=directories.count?[directories[0] stringByAppendingPathComponent:@"SweetNativeMetal"]:nil;
    if(cache && ![[NSFileManager defaultManager] createDirectoryAtPath:cache withIntermediateDirectories:YES attributes:nil error:nil])cache=nil;
    void *iokit=dlopen("/System/Library/Frameworks/IOKit.framework/IOKit",RTLD_NOW|RTLD_LOCAL);
    if(!iokit)return nil;
    auto registryIDFn=(int (*)(unsigned,uint64_t *))dlsym(iokit,"IORegistryEntryGetRegistryEntryID");
    uint64_t registryID=0;
    if(!registryIDFn || registryIDFn(port,&registryID)!=0 || !registryID)return nil;
    id device=native_bridge_metal_open(loader,cache.fileSystemRepresentation,registryID,nullptr);
    if(!device)NSLog(@"sweet-metal: native renderer initialization failed");
    return device;
}
@end
