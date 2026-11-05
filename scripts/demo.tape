Output demo.gif
Set FontSize 14
Set Width 1100
Set Height 640
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrains Mono"
Set TypingSpeed 18ms
Set Framerate 24
Set Padding 16
Set WindowBar Colorful
Set Shell bash
Hide
Type `export PATH="$KF_BIN_DIR:$PATH"`
Enter
Type `cd "$KF_DEMO_HOME"`
Enter
Type `export PS1='demo$ '`
Enter
Type `clear`
Enter
Show

Type `printf 'kube-foundry v1.1.0 (offline validate; no kind)\n'`
Enter
Sleep 0.8s

Type `make check-chart`
Enter
Sleep 2.2s

Type `make validate`
Enter
Sleep 3.0s

Sleep 1.2s
