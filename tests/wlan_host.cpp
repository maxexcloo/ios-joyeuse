// XNU API boundary model: run the actual patched callbacks with synthetic frames.
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

using Bytes = std::vector<uint8_t>;
using errno_t = int;
using u_int32_t = uint32_t;
using ifnet_t = void *;
struct mbuf {
    Bytes storage;
    size_t offset = 0, length = 0, packet_length = 0;
    void *header = nullptr;
    ifnet_t receiver = nullptr;
    mbuf *next = nullptr;
    bool external = false;
};
using mbuf_t = mbuf *;
struct ifnet_stat_increment_param { uint32_t packets_in = 0, bytes_in = 0; };
constexpr int MBUF_DONTWAIT = 0, MBUF_TYPE_DATA = 0, MBUF_EXT = 1;
constexpr int ETHER_HDR_LEN = 14, DLT_EN10MB = 1;
enum Allocation { Normal, HeaderFailure, ClusterFailure, NoCluster, SmallCluster };
static Allocation allocation;
static unsigned live, allocations, inputs, taps_in, taps_out;
static int interface;
static ifnet_t wl_ifp = &interface;
static bool radio_ready = true;
static Bytes received, captured_in, captured_out, transmitted;

int mbuf_gethdr(int, int, mbuf_t *m) {
    ++allocations;
    if (allocation == HeaderFailure) return ENOMEM;
    *m = new mbuf; ++live; return 0;
}
int mbuf_mclget(int, int, mbuf_t *m) {
    if (allocation == ClusterFailure) return ENOMEM;
    (*m)->storage.resize(allocation == SmallCluster ? 8 : 2048);
    (*m)->external = allocation != NoCluster;
    return 0;
}
void mbuf_freem(mbuf_t m) {
    while (m) { auto next = m->next; delete m; assert(live); --live; m = next; }
}
void m_freem(mbuf_t m) { mbuf_freem(m); }
int mbuf_flags(mbuf_t m) { return m->external ? MBUF_EXT : 0; }
size_t mbuf_maxlen(mbuf_t m) { return m->storage.size(); }
void *mbuf_data(mbuf_t m) { return m->storage.data() + m->offset; }
size_t mbuf_pkthdr_len(mbuf_t m) { return m->packet_length; }
void mbuf_setlen(mbuf_t m, size_t n) { assert(n <= m->storage.size()); m->length = n; }
void mbuf_pkthdr_setlen(mbuf_t m, size_t n) { m->packet_length = n; }
void mbuf_pkthdr_setrcvif(mbuf_t m, ifnet_t p) { m->receiver = p; }
void mbuf_pkthdr_setheader(mbuf_t m, void *p) { m->header = p; }
void mbuf_pkthdr_adjustlen(mbuf_t m, int n) {
    assert(n >= 0 || m->packet_length >= static_cast<size_t>(-n)); m->packet_length += n;
}
int mbuf_setdata(mbuf_t m, void *p, size_t n) {
    auto offset = static_cast<uint8_t *>(p) - m->storage.data();
    assert(offset >= 0 && static_cast<size_t>(offset) + n <= m->storage.size());
    m->offset = offset; m->length = n; return 0;
}
Bytes packet_bytes(mbuf_t m) {
    Bytes data;
    for (; m; m = m->next) {
        auto begin = m->storage.begin() + m->offset;
        data.insert(data.end(), begin, begin + m->length);
    }
    return data;
}
void m_copydata(mbuf_t m, int offset, int length, void *out) {
    auto data = packet_bytes(m);
    assert(offset >= 0 && length >= 0 && static_cast<size_t>(offset + length) <= data.size());
    memcpy(out, data.data() + offset, length);
}
void bpf_tap_in(ifnet_t p, int dlt, mbuf_t m, void *header, size_t n) {
    assert(p == wl_ifp && dlt == DLT_EN10MB && header && n == ETHER_HDR_LEN);
    auto h = static_cast<uint8_t *>(header);
    captured_in.assign(h, h + n);
    auto data = packet_bytes(m); captured_in.insert(captured_in.end(), data.begin(), data.end());
    ++taps_in;
}
void bpf_tap_out(ifnet_t p, int dlt, mbuf_t m, void *header, size_t n) {
    assert(p == wl_ifp && dlt == DLT_EN10MB && !header && !n);
    captured_out = packet_bytes(m); ++taps_out;
}
int ifnet_input(ifnet_t p, mbuf_t m, ifnet_stat_increment_param *stats) {
    assert(p == wl_ifp && m->receiver == p && m->header == m->storage.data());
    assert(mbuf_data(m) == static_cast<uint8_t *>(m->header) + ETHER_HDR_LEN);
    received = packet_bytes(m);
    assert(m->packet_length == received.size());
    assert(stats->packets_in == 1 && stats->bytes_in == received.size() + ETHER_HDR_LEN);
    ++inputs; mbuf_freem(m); return 0;
}
bool topaz_wlan_transmit(const uint8_t *p, size_t n) { transmitted.assign(p, p + n); return radio_ready; }

// PRODUCTION CALLBACKS

Bytes dhcp_discover() {
    Bytes f(14 + 20 + 8 + 244, 0);
    std::fill(f.begin(), f.begin() + 6, 0xff);
    f[6] = 2; f[11] = 1; f[12] = 8; // locally administered source; IPv4
    auto ip = f.data() + 14;
    ip[0] = 0x45; ip[2] = 1; ip[3] = 16; ip[8] = 64; ip[9] = 17;
    std::fill(ip + 16, ip + 20, 0xff);
    unsigned sum = 0;
    for (int i = 0; i < 20; i += 2) sum += (ip[i] << 8) | ip[i + 1];
    while (sum >> 16) sum = (sum & 0xffff) + (sum >> 16);
    ip[10] = (~sum >> 8) & 0xff; ip[11] = ~sum & 0xff;
    auto udp = ip + 20;
    udp[1] = 68; udp[3] = 67; udp[5] = 252;
    auto bootp = udp + 8;
    bootp[0] = 1; bootp[1] = 1; bootp[2] = 6; bootp[4] = 0x12; bootp[7] = 0x78;
    bootp[10] = 0x80; bootp[28] = 2; bootp[33] = 1;
    const uint8_t options[] = {99, 130, 83, 99, 53, 1, 1, 255};
    memcpy(bootp + 236, options, sizeof(options));
    return f;
}
mbuf_t outgoing(const Bytes &frame, size_t split) {
    auto first = new mbuf; ++live;
    first->storage.assign(frame.begin(), frame.begin() + split);
    first->length = split; first->packet_length = frame.size();
    if (split < frame.size()) {
        first->next = new mbuf; ++live;
        first->next->storage.assign(frame.begin() + split, frame.end());
        first->next->length = frame.size() - split;
    }
    return first;
}
void reset() {
    assert(live == 0); allocation = Normal; radio_ready = true; wl_ifp = &interface;
    allocations = inputs = taps_in = taps_out = 0;
    received.clear(); captured_in.clear(); captured_out.clear(); transmitted.clear();
}
int main() {
    auto dhcp = dhcp_discover();
    for (auto frame : {Bytes(14, 0x5a), dhcp, Bytes(1514, 0xa5)}) {
        reset(); wl_rx(frame.data(), frame.size());
        assert(inputs == 1 && taps_in == 1 && captured_in == frame);
        assert(received == Bytes(frame.begin() + 14, frame.end()));
        for (size_t split : {size_t(0), size_t(7), frame.size()}) {
            reset(); assert(wl_output(wl_ifp, outgoing(frame, split)) == 0);
            assert(taps_out == 1 && captured_out == frame && transmitted == frame && live == 0);
        }
    }
    for (auto mode : {HeaderFailure, ClusterFailure, NoCluster, SmallCluster}) {
        reset(); allocation = mode; wl_rx(dhcp.data(), dhcp.size());
        assert(live == 0 && inputs == 0 && taps_in == 0);
    }
    for (size_t n : {size_t(0), size_t(13), size_t(1515)}) {
        reset(); Bytes frame(n, 0); wl_rx(frame.data(), n);
        assert(allocations == 0 && inputs == 0 && taps_in == 0);
        assert(wl_output(wl_ifp, outgoing(frame, n)) == EMSGSIZE);
        assert(live == 0 && taps_out == 0 && transmitted.empty());
    }
    reset(); wl_ifp = nullptr; wl_rx(dhcp.data(), dhcp.size());
    assert(allocations == 0 && inputs == 0);
    reset(); radio_ready = false;
    assert(wl_output(wl_ifp, outgoing(dhcp, 7)) == ENETDOWN && live == 0);
    puts("WLAN callbacks: frame delivery, BPF capture, chained output and allocation ownership passed");
}
