# Connecting to Plotter Network Shares (Samba over mDNS)

A step-by-step guide to connect to a public/guest Samba network share broadcasted over mDNS under the hostname `plotter` (or `plotter.local`).

## Table of Contents
- [iOS (iPhone / iPad)](#ios-iphone--ipad)
- [Android](#android)
- [Windows (10 / 11)](#windows-10--11)
- [Ubuntu / Linux (GNOME)](#ubuntu--linux-gnome)
- [Troubleshooting & mDNS Tips](#troubleshooting--mdns-tips)

## iOS (iPhone / iPad)
iOS includes native support for SMB shares directly within the **Files** app.

1. Open the **Files** app.
2. Tap the **three dots (...)** icon in the top-right corner (under the **Browse** tab).
3. Select **Connect to Server**.
4. Enter:

```text
smb://plotter.local
```

   If `plotter.local` does not resolve, try:

```text
smb://plotter
```

5. Tap **Connect**.
6. Select **Guest** as the authentication type and tap **Next**.

## Android
Most stock Android file managers do not resolve mDNS names natively.
Using a free client like **Cx File Explorer** or **Total Commander** is recommended.

### Using Cx File Explorer
1. Install **Cx File Explorer** from Google Play Store.
2. Open the app and go to the **Network** tab.
3. Tap **+** and select **LAN / SMB**.
4. In the **Host** field, enter:

```text
plotter.local
```

5. Check **Anonymous / Guest**.
6. Tap **OK** to access the share.

## Windows (10 / 11)
Windows supports mDNS hostnames natively (Windows 10 build 1803+).

### Quick Access (Run Dialog)
1. Press `Win + R`.
2. Enter:

```text
\\plotter.local\
```

   or

```text
\\plotter\
```

3. Press **Enter**.

### Persistent Drive Mapping
1. Open **File Explorer** (`Win + E`) and click **This PC**.
2. Select **Map network drive** from the toolbar/menu.
3. Choose a drive letter (for example, `Z:`).
4. In **Folder**, enter:

```text
\\plotter.local\SHARE_NAME
```

5. Check **Reconnect at sign-in** and click **Finish**.

## Ubuntu / Linux (GNOME)
Ubuntu resolves `.local` mDNS hostnames via Avahi.

1. Open **Files (Nautilus)**.
2. In the left sidebar, click **Other Locations**.
3. At the bottom, in **Connect to Server**, enter:

```text
smb://plotter.local/
```

4. Click **Connect**.
5. Select **Anonymous** as the authentication method and confirm.

## Troubleshooting & mDNS Tips
- If `plotter.local` is not found, try `plotter` or use the device IP address.
- Confirm both devices are on the same subnet/VLAN.
- Verify SMB service is running on the tablet/host.
- Restart mDNS/Bonjour services if name resolution is intermittent.
