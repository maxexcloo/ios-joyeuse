/*
 * First userspace program for SWEET bring-up: mockfs serves the RAM disk
 * itself as /sbin/launchd, so this static binary is PID 1. It proves that
 * exec, the user/kernel boundary, devfs and the console all work, then
 * stays alive (init exiting panics the kernel).
 *
 * tools/mkinit.py wraps the assembled __text into a static Mach-O, so this
 * must stay position independent with no relocations and no writable data:
 * every reference is adr (PC-relative), the PID digit lives on the stack.
 *
 * Raw XNU syscalls: number in x16, svc #0x80, carry set on error.
 */
#define SYS_exit	1
#define SYS_fork	2
#define SYS_wait4	7
#define SYS_setuid	23
#define SYS_socket	97
#define SYS_setsockopt	105
#define SYS_mac_syscall	381
#define SYS_write	4
#define SYS_open	5
#define SYS_getpid	20
#define SYS_select	93
#define O_RDWR		2

	.text
	.globl	_start
	.p2align 2
_start:
	/*
	 * The kernel enters a static binary with sp at argc, aligned only to
	 * what the argument/apple strings happened to need. Using a misaligned
	 * sp as a base register raises an SP alignment fault (SIGBUS) on real
	 * hardware (QEMU does not check), so align it like crt0/dyld do.
	 */
	mov	x9, sp
	and	x9, x9, #~15
	mov	sp, x9

	adr	x0, path
	mov	x1, #O_RDWR
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	hang			/* no console: nothing to report to */
	mov	x19, x0

	adr	x1, hello
	adr	x2, hello_tail
	sub	x2, x2, x1
	bl	write_console

	mov	x16, #SYS_getpid
	svc	#0x80
	add	w0, w0, #'0'		/* PID 1 expected: one digit */
	sub	sp, sp, #16
	strb	w0, [sp]
	mov	x1, sp
	mov	x2, #1
	bl	write_console
	add	sp, sp, #16

	adr	x1, hello_tail
	adr	x2, alive
	sub	x2, x2, x1
	bl	write_console

	bl	test_amfi
	bl	test_delegate

tick:
	/* select(0, NULL, NULL, NULL, &5s) as a portable sleep */
	mov	x0, #0
	mov	x1, #0
	mov	x2, #0
	mov	x3, #0
	adr	x4, five_sec
	mov	x16, #SYS_select
	svc	#0x80

	adr	x1, alive
	adr	x2, alive_end
	sub	x2, x2, x1
	bl	write_console
	b	tick

/* Exercise the real policy syscall, including restricted/encrypted inputs. */
test_amfi:
	stp	x29, x30, [sp, #-64]!
	mov	x20, #0
1:
	str	x20, [sp, #16]
	add	x0, sp, #32
	str	x0, [sp, #24]
	adr	x0, amfi_name
	mov	x1, #0x5a
	add	x2, sp, #16
	mov	x16, #SYS_mac_syscall
	svc	#0x80
	b.cs	amfi_failed
	ldr	x0, [sp, #32]
	mov	x1, #0xfb
	cmp	x20, #0
	mov	x2, #1
	csel	x1, x1, x2, eq
	cmp	x0, x1
	b.ne	amfi_failed
	add	x20, x20, #2
	cmp	x20, #8
	b.lo	1b
	/* A bad output pointer must be rejected, rather than dereferenced. */
	str	xzr, [sp, #24]
	adr	x0, amfi_name
	mov	x1, #0x5a
	add	x2, sp, #16
	mov	x16, #SYS_mac_syscall
	svc	#0x80
	b.cc	amfi_failed
	cmp	x0, #14
	b.ne	amfi_failed
	adr	x0, amfi_name
	mov	x1, #0x5a
	mov	x2, #0
	mov	x16, #SYS_mac_syscall
	svc	#0x80
	b.cc	amfi_failed
	cmp	x0, #14
	b.ne	amfi_failed
	adr	x0, amfi_name
	mov	x1, #0x5b
	mov	x2, #0
	mov	x16, #SYS_mac_syscall
	svc	#0x80
	b.cc	amfi_failed
	cmp	x0, #103
	b.ne	amfi_failed
	adr	x1, amfi_ok
	adr	x2, amfi_ok_end
	b	amfi_report
amfi_failed:
	adr	x1, amfi_bad
	adr	x2, amfi_bad_end
amfi_report:
	sub	x2, x2, x1
	bl	write_console
	ldp	x29, x30, [sp], #64
	ret

/* A non-root networking child delegates a socket to PID 1, as WebKit does. */
test_delegate:
	stp	x29, x30, [sp, #-32]!
	mov	x16, #SYS_fork
	svc	#0x80
	b.cs	delegate_failed
	cbnz	x1, delegate_child
	add	x1, sp, #16
	mov	x2, #0
	mov	x3, #0
	mov	x16, #SYS_wait4
	svc	#0x80
	b.cs	delegate_failed
	ldr	w0, [sp, #16]
	cbnz	w0, delegate_failed
	adr	x1, delegate_ok
	adr	x2, delegate_ok_end
	b	delegate_report
delegate_failed:
	adr	x1, delegate_bad
	adr	x2, delegate_bad_end
delegate_report:
	sub	x2, x2, x1
	bl	write_console
	ldp	x29, x30, [sp], #32
	ret
delegate_child:
	mov	x0, #501
	mov	x16, #SYS_setuid
	svc	#0x80
	b.cs	child_failed
	mov	x0, #2                 /* AF_INET */
	mov	x1, #2                 /* SOCK_DGRAM */
	mov	x2, #0
	mov	x16, #SYS_socket
	svc	#0x80
	b.cs	child_failed
	mov	x1, #0xffff            /* SOL_SOCKET */
	mov	x2, #0x1107            /* SO_DELEGATED */
	mov	w3, #1
	str	w3, [sp, #16]
	add	x3, sp, #16
	mov	x4, #4
	mov	x16, #SYS_setsockopt
	svc	#0x80
	b.cs	child_failed
	mov	x0, #0
	b	child_exit
child_failed:
	mov	x0, #1
child_exit:
	mov	x16, #SYS_exit
	svc	#0x80
	b	hang

/* write(x19, x1, x2) */
write_console:
	mov	x0, x19
	mov	x16, #SYS_write
	svc	#0x80
	ret

hang:
	b	hang

	.p2align 3
five_sec:
	.quad	5			/* tv_sec */
	.quad	0			/* tv_usec (int32 + padding) */
path:
	.asciz	"/dev/console"
hello:
	.ascii	"\n*** SWEET userspace: init running as PID "
hello_tail:
	.ascii	" ***\n"
alive:
	.ascii	"SWEET init: still alive\n"
alive_end:

amfi_name:
	.asciz "AMFI"
amfi_ok:
	.ascii "SWEET test: AMFI policy PASS\n"
amfi_ok_end:
amfi_bad:
	.ascii "SWEET test: AMFI policy FAIL\n"
amfi_bad_end:
delegate_ok:
	.ascii "SWEET test: non-root socket delegation PASS\n"
delegate_ok_end:
delegate_bad:
	.ascii "SWEET test: non-root socket delegation FAIL\n"
delegate_bad_end:
