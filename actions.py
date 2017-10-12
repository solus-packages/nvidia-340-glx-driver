#!/usr/bin/python
import os.path

NoStrip = ["/"]

from pisi.actionsapi import get, shelltools, pisitools, autotools, kerneltools
import commands

# Required... built in tandem with kernel update
kernel_trees = {
    "linux-lts": "4.9.56-52.lts",
    "linux-current": "4.13.6-25.current"
}

def patch_dir(kernel):
    """ Handle patching for each kernel type """
    olddir = os.getcwd()
    shelltools.cd(kernel)
    shelltools.system("patch -p0 < ../linux49.patch")

    # See: https://github.com/Hoshpak/void-packages/blob/master/srcpkgs/nvidia340/files/linux-4.12.patch
    # And: https://devtalk.nvidia.com/default/topic/1008771/linux/nvidia-340-xx-compile-error-with-kernel-4-12-rc1/post/5179612/#5179612
    if kernel == "linux-current":
        shelltools.system("patch -p0 < ../4.10.0_kernel.patch")
        shelltools.system("patch -p0 < ../linux-4.11.patch")
        shelltools.system("patch -p0 < ../linux-4.12.patch")
    else:
        shelltools.system("patch -p0 < ../nv-drm.patch")
    shelltools.cd(olddir)

def setup():
    """ Extract the NVIDIA binary for each kernel tree and rename it each time
        to match the desired tree, to ensure we don't have them conflicting. """
    blob = "NVIDIA-Linux-x86_64-%s" % get.srcVERSION()
    for kernel in kernel_trees:
        shelltools.system("sh %s.run --extract-only" % blob)
        shelltools.move(blob, kernel)
        patch_dir(kernel)

def build():
    for kernel in kernel_trees:
        build_kernel(kernel)

def build_kernel(typename):
    version = kernel_trees[typename]
    olddir = os.getcwd()
    shelltools.cd(typename + "/kernel")
    autotools.make("\"SYSSRC=/lib64/modules/%s/build\" module" % version)
    shelltools.cd("uvm")
    autotools.make("\"SYSSRC=/lib64/modules/%s/build\" module" % version)
    shelltools.cd(olddir)

def install_kernel(typename):
    olddir = os.getcwd()
    version = kernel_trees[typename]

    kdir = "/lib64/modules/%s/kernel/drivers/video" % version
    # kernel portion, i.e. /lib/modules/3.19.7/kernel/drivers/video/nvidia.ko
    shelltools.cd(typename + "/kernel")
    pisitools.dolib_a("nvidia.ko", kdir)
    shelltools.cd("uvm")
    pisitools.dolib_a("nvidia-uvm.ko", kdir)

    shelltools.cd(olddir)

def install_modalias(typename):
    """ install_modalias will generate modaliases for the given tree, which will
        only be linux-lts for now
    """
    olddir = os.getcwd()
    shelltools.cd(typename + "/kernel")

    # install modalias
    pisitools.dodir("/usr/share/doflicky/modaliases")
    modfile = "%s/usr/share/doflicky/modaliases/%s.modaliases" % (get.installDIR(), get.srcNAME())
    shelltools.system("sh -e ../../nvidia_supported nvidia %s ../README.txt nvidia.ko > %s" %
                     (get.srcNAME(), modfile))

    shelltools.cd(olddir)

def link_install(lib, libdir='/usr/lib', abi='1', cdir='.'):
    ''' Install a library with necessary links '''
    pisitools.dolib("%s/%s.so.%s" % (cdir, lib, get.srcVERSION()), libdir)
    pisitools.dosym("%s/%s.so.%s" % (libdir, lib, get.srcVERSION()), "%s/%s.so.%s" % (libdir, os.path.basename(lib), abi))
    pisitools.dosym("%s/%s.so.%s" % (libdir, lib, abi), "%s/%s.so" % (libdir, os.path.basename(lib)))
        
def install():
    for kernel in kernel_trees:
        install_kernel(kernel)
    install_modalias("linux-lts")

    # glx portion, always build from the linux-lts tree
    shelltools.cd("linux-lts")

    pisitools.dolib("nvidia_drv.so", "/usr/lib/xorg/modules/drivers")

    # libGL replacement - conflicts
    libs = ["libGL", "libEGL", "libGLESv1_CM", "libGLESv2", "libglx"]
    for lib in libs:
        abi = '2' if lib == "libGLESv2" else "1"
        link_install(lib, "/usr/lib/glx-provider/nvidia", abi)
        if lib != "libglx":
            link_install(lib, "/usr/lib32/glx-provider/nvidia", abi, cdir='32')

    # non-conflict libraries
    libs =  ["libnvidia-glcore", "libnvidia-eglcore", "libnvidia-glsi",
        "libnvidia-ifr", "libnvidia-fbc", "libnvidia-encode",
        "libnvidia-ml", "libcuda", "libnvcuvid"]

    native_libs = ["libnvidia-cfg"]
    for lib in libs:
        link_install(lib)
        link_install(lib, libdir='/usr/lib32', cdir='32')
    for lib in native_libs:
        link_install(lib)

    # vdpau provider
    link_install("libvdpau_nvidia", "/usr/lib/vdpau")
    link_install("libvdpau_nvidia", "/usr/lib32/vdpau", cdir='32')

    # TLS
    link_install("tls/libnvidia-tls")
    link_install("tls/libnvidia-tls", libdir='/usr/lib32', cdir='32')

    # binaries
    bins = ["nvidia-debugdump", "nvidia-xconfig", "nvidia-settings",
        "nvidia-bug-report.sh", "nvidia-smi", "nvidia-modprobe",
        "nvidia-cuda-mps-control", "nvidia-cuda-mps-server",
        "nvidia-persistenced"]
    for bin in bins:
        pisitools.dobin(bin)

    # data files
    pisitools.dosed("nvidia-settings.desktop", "__UTILS_PATH__", "/usr/bin")
    pisitools.dosed("nvidia-settings.desktop", "__PIXMAP_PATH__", "/usr/share/pixmaps")
    pisitools.dosed("nvidia-settings.desktop", "Settings", "System")
    pisitools.insinto("/usr/share/applications", "nvidia-settings.desktop")
    pisitools.insinto("/usr/share/pixmaps", "nvidia-settings.png")
    pisitools.insinto("/usr/share/OpenCL/vendors", "nvidia.icd")

    # Blacklist nouveau
    pisitools.dodir("/usr/lib/modprobe.d")
    shelltools.echo("%s/usr/lib/modprobe.d/nvidia.conf" % get.installDIR(),
        "blacklist nouveau")

    # systemd/persistencd
    shelltools.system("tar xf nvidia-persistenced-init.tar.bz2")
    pisitools.insinto("/usr/lib/systemd/system",
                      "nvidia-persistenced-init/systemd/nvidia-persistenced.service.template",
                      destinationFile="nvidia-persistenced.service")
    pisitools.dosed("%s/usr/lib/systemd/system/nvidia-persistenced.service" % get.installDIR(),
                    "__USER__", "nvidia-persistenced")
