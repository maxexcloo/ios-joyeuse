#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <strings.h>

// PRODUCTION TYPES

struct Mapping {
    uint64_t address;
    uint64_t getAddress() const { return address; }
};
struct SweetSurfaceRef { Mapping *data, *state; };

// PRODUCTION SERIALISER

uint32_t get32(const uint8_t *client, unsigned offset) {
    uint32_t result;
    memcpy(&result, client + offset, sizeof(result));
    return result;
}
int main() {
    SweetSurface surface = {};
    surface.id = 7;
    surface.width = 64;
    surface.height = 32;
    surface.bytesPerRow = 256;
    surface.allocSize = 8192;
    surface.bytesPerElement = 4;
    surface.elementWidth = surface.elementHeight = 1;
    surface.planeCount = 2;
    surface.planes[0] = {64, 32, 128, 0, 4096, 2, 1, 1};
    surface.planes[1] = {32, 16, 64, 4096, 1024, 2, 2, 2};
    Mapping data{0x12340000}, state{0x56780000};
    SweetSurfaceRef ref{&data, &state};
    std::array<uint8_t, 0x68 + SWEET_SURFACE_RESULT_SIZE> client{};
    sweet_surface_fill_result(&surface, &ref, client.data() + 0x68);
    assert(get32(client.data(), 0x88) == 64);
    assert(get32(client.data(), 0x8c) == 32);
    assert(get32(client.data(), 0x90) == 256);
    // Native 20H392 plane getters use these client offsets and a 0x80 stride.
    for (unsigned i = 0; i < surface.planeCount; ++i) {
        const auto &p = surface.planes[i];
        unsigned delta = i * 0x80;
        assert(get32(client.data(), 0xd0 + delta) == p.width);
        assert(get32(client.data(), 0xd4 + delta) == p.height);
        assert(get32(client.data(), 0xe0 + delta) == p.bytesPerRow);
        assert(get32(client.data(), 0xdc + delta) == p.offset);
        assert(get32(client.data(), 0xe4 + delta) == p.size);
        assert(client[0xe8 + delta] == p.bytesPerElement);
        assert(client[0xea + delta] == p.elementWidth);
        assert(client[0xeb + delta] == p.elementHeight);
    }
    surface.planeCount = 0;
    sweet_surface_fill_result(&surface, &ref, client.data() + 0x68);
    assert(get32(client.data(), 0x90) == 256);
}
