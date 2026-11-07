// Model only UIO/controller boundaries; the raw callbacks come from numbered patches.
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>
#ifndef __unused
#define __unused __attribute__((unused))
#endif
#define MIN(a, b) ((a) < (b) ? (a) : (b))
constexpr uint32_t UFS_BLOCK = 4096, BOUNCE_SIZE = 16384, DMA_BOUNCE = 0;
constexpr int Z_WAITOK = 0;
using Bytes = std::vector<uint8_t>;
struct IOV { uint8_t *base; size_t size; };
struct uio { std::vector<IOV> iovs; size_t index = 0, resid = 0; int64_t offset; bool write; };
using uio_t = uio *;
static struct { uint64_t nblocks = 12, first_block = 3; uint32_t secsize = 512; bool writable = true; uintptr_t dma; } su;
static Bytes disk(20 * UFS_BLOCK), bounce(BOUNCE_SIZE);
static unsigned reads, writes, allocations;
static bool locked, fail_read, fail_write, fail_alloc, fail_duplicate;
static size_t fault_after = std::numeric_limits<size_t>::max();
static int sweet_ufs_lock;
int64_t uio_offset(uio_t u) { return u->offset; }
int64_t uio_resid(uio_t u) { return u->resid; }
size_t uio_curriovlen(uio_t u) { return u->index < u->iovs.size() ? u->iovs[u->index].size : 0; }
void uio_update(uio_t u, size_t n) {
    if (n) {
        assert(u->index < u->iovs.size() && n <= u->iovs[u->index].size && n <= u->resid);
        u->iovs[u->index].base += n; u->iovs[u->index].size -= n; u->resid -= n; u->offset += n;
    }
    while (u->index < u->iovs.size() && u->iovs[u->index].size == 0) ++u->index;
}
uio_t uio_duplicate(uio_t u) { return fail_duplicate ? nullptr : new uio(*u); }
void uio_free(uio_t u) { delete u; }
int uiomove(void *buffer, int length, uio_t u) {
    assert(!locked); // Copy faults may need the same disk to page user memory in.
    auto p = static_cast<uint8_t *>(buffer);
    size_t done = 0, n = length;
    while (done < n) {
        uio_update(u, 0);
        size_t step = std::min({n - done, uio_curriovlen(u), fault_after});
        if (!step) return EFAULT;
        if (u->write) memcpy(p + done, u->iovs[u->index].base, step);
        else memcpy(u->iovs[u->index].base, p + done, step);
        uio_update(u, step); done += step; fault_after -= step;
    }
    return 0;
}
void *kalloc_data(size_t n, int) { if (fail_alloc) return nullptr; ++allocations; return malloc(n); }
void kfree_data(void *p, size_t) { assert(allocations); --allocations; free(p); }
void lck_mtx_lock(int *) { assert(!locked); locked = true; }
void lck_mtx_unlock(int *) { assert(locked); locked = false; }
int ufs_read_blocks(uint64_t lba, uint32_t count) {
    assert(locked && count && count * UFS_BLOCK <= BOUNCE_SIZE);
    assert(lba >= su.first_block && lba + count <= su.first_block + su.nblocks);
    ++reads; if (fail_read) return EIO;
    memcpy(bounce.data(), disk.data() + lba * UFS_BLOCK, count * UFS_BLOCK); return 0;
}
int ufs_write_blocks(uint64_t lba, uint32_t count) {
    assert(locked && count && count * UFS_BLOCK <= BOUNCE_SIZE);
    assert(lba >= su.first_block && lba + count <= su.first_block + su.nblocks);
    ++writes; if (fail_write) return EIO;
    memcpy(disk.data() + lba * UFS_BLOCK, bounce.data(), count * UFS_BLOCK); return 0;
}

// PRODUCTION CALLBACKS

uio request(Bytes &bytes, int64_t offset, bool write, size_t split) {
    uio u; u.offset = offset; u.resid = bytes.size(); u.write = write;
    u.iovs = {{bytes.data(), split}, {bytes.data() + split, 0}, {bytes.data() + split, bytes.size() - split}};
    return u;
}
void reset() {
    assert(!locked && !allocations);
    su.dma = reinterpret_cast<uintptr_t>(bounce.data()); su.writable = true;
    reads = writes = 0; fail_read = fail_write = fail_alloc = fail_duplicate = false;
    fault_after = std::numeric_limits<size_t>::max();
    for (size_t i = 0; i < disk.size(); ++i) disk[i] = (i * 23 + i / 251) & 255;
}
int main() {
    for (size_t offset : {size_t(0), size_t(30), size_t(4090), size_t(17001)}) {
        reset(); Bytes output(19001); auto u = request(output, offset, false, 37);
        assert(sweet_ufs_read(0, &u, 0) == 0 && !u.resid && u.offset == static_cast<int64_t>(offset + output.size()));
        assert(std::equal(output.begin(), output.end(), disk.begin() + su.first_block * UFS_BLOCK + offset));
        assert(!locked && !allocations);
    }
    reset(); Bytes output(100, 0xa5); auto u = request(output, su.nblocks * UFS_BLOCK - 11, false, 3);
    assert(sweet_ufs_read(0, &u, 0) == 0 && u.resid == 89);
    assert(std::all_of(output.begin() + 11, output.end(), [](uint8_t v) { return v == 0xa5; }));
    reset(); Bytes input(3 * UFS_BLOCK, 0xe7); auto original = disk;
    u = request(input, 512, true, 31);
    assert(sweet_ufs_write(0, &u, 0) == 0 && !u.resid);
    auto start = su.first_block * UFS_BLOCK + 512;
    assert(std::equal(disk.begin(), disk.begin() + start, original.begin()));
    assert(std::equal(input.begin(), input.end(), disk.begin() + start));
    assert(std::equal(disk.begin() + start + input.size(), disk.end(), original.begin() + start + input.size()));
    reset(); su.writable = false; u = request(input, 0, true, 0);
    assert(sweet_ufs_write(0, &u, 0) == EROFS && !writes && u.resid == input.size());
    for (int64_t offset : {int64_t(-1), int64_t(30), int64_t(su.nblocks * UFS_BLOCK - 512)}) {
        reset(); u = request(input, offset, true, 0);
        assert(sweet_ufs_write(0, &u, 0) == EINVAL && !writes && !reads && u.resid == input.size());
    }
    reset(); Bytes short_write(513); u = request(short_write, 0, true, 0);
    assert(sweet_ufs_write(0, &u, 0) == EINVAL && !writes);
    reset(); fault_after = 17; output.assign(100, 0); u = request(output, 31, false, 9);
    assert(sweet_ufs_read(0, &u, 0) == EFAULT && u.resid == 83 && u.offset == 48);
    reset(); fault_after = 17; u = request(input, 512, true, 9); original = disk;
    assert(sweet_ufs_write(0, &u, 0) == EFAULT && u.resid == input.size() && u.offset == 512 && !writes && disk == original);
    reset(); Bytes large(2 * BOUNCE_SIZE, 0x37); original = disk;
    fault_after = BOUNCE_SIZE + 17; u = request(large, 0, true, 9);
    assert(sweet_ufs_write(0, &u, 0) == EFAULT && u.resid == BOUNCE_SIZE && u.offset == BOUNCE_SIZE && writes == 1);
    start = su.first_block * UFS_BLOCK;
    assert(std::equal(large.begin(), large.begin() + BOUNCE_SIZE, disk.begin() + start));
    assert(std::equal(disk.begin() + start + BOUNCE_SIZE, disk.end(), original.begin() + start + BOUNCE_SIZE));
    reset(); fail_write = true; u = request(input, 512, true, 9);
    assert(sweet_ufs_write(0, &u, 0) == EIO && u.resid == input.size() && u.offset == 512);
    reset(); fail_read = true; u = request(output, 31, false, 0);
    assert(sweet_ufs_read(0, &u, 0) == EIO && u.resid == output.size());
    reset(); fail_duplicate = true; u = request(input, 512, true, 0);
    assert(sweet_ufs_write(0, &u, 0) == ENOMEM && !writes && !reads);
    reset(); fail_alloc = true; u = request(output, su.nblocks * UFS_BLOCK, false, 0);
    assert(sweet_ufs_read(0, &u, 0) == 0 && !reads && u.resid == output.size());
    reset(); fail_alloc = true; u = request(output, 31, false, 0);
    assert(sweet_ufs_read(0, &u, 0) == ENOMEM && !reads);
    assert(!locked && !allocations);
    puts("Raw UFS: byte offsets, scatter I/O, EOF, write fences, copy faults and device errors passed");
}
