# Maintainer: Aasray <aasray@gmail.com>
pkgname=gigabyte-keyboard-ctl
pkgver=1.0.0
pkgrel=1
pkgdesc="RGB keyboard backlight control for the GIGABYTE GAMING A16 (CTH)"
arch=('any')
url="https://github.com/aasray123/gigabyte-keyboard-ctl"
license=('MIT')
depends=('python')
optdepends=('python-pyqt6: graphical control panel')
install="$pkgname.install"
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('80d0c17c375fcd6138561856a0347633e2606a375d610c6d75bfc5fc42fdd530')

package() {
    cd "$srcdir/$pkgname-$pkgver"

    install -Dm755 bin/gigabyte-kbd "$pkgdir/usr/bin/gigabyte-kbd"

    install -d "$pkgdir/usr/lib/gigabyte-keyboard-ctl"
    cp -a gigabyte_kbd "$pkgdir/usr/lib/gigabyte-keyboard-ctl/"
    find "$pkgdir/usr/lib/gigabyte-keyboard-ctl" \
        -type d -name __pycache__ -prune -exec rm -rf {} +

    install -Dm644 data/gigabyte-kbd.desktop \
        "$pkgdir/usr/share/applications/gigabyte-kbd.desktop"
    install -Dm644 udev/99-gigabyte-kbd.rules \
        "$pkgdir/usr/lib/udev/rules.d/99-gigabyte-kbd.rules"
    install -Dm644 systemd/gigabyte-kbd.service \
        "$pkgdir/usr/lib/systemd/user/gigabyte-kbd.service"

    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}
