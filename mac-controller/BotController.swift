import Cocoa
import Foundation

final class BotController: NSObject, NSApplicationDelegate {
    let botPath = "/Users/eroldemirtas276/Python Test/bot.py"
    let pythonPath = "/Users/eroldemirtas276/Python Test/.venv/bin/python"
    let envPath = "/Users/eroldemirtas276/Python Test/.env"
    let logPath = (NSHomeDirectory() as NSString).appendingPathComponent("Library/Logs/eAI Discord Bot.log")
    let plistPath = (NSHomeDirectory() as NSString).appendingPathComponent("Library/LaunchAgents/com.eai.discordbot.plist")
    let appPath = Bundle.main.bundlePath

    var statusItem: NSStatusItem!
    var process: Process?
    var startItem: NSMenuItem!
    var stopItem: NSMenuItem!
    var restartItem: NSMenuItem!
    var autoStartItem: NSMenuItem!

    func envValue(_ key: String) -> String {
        guard let text = try? String(contentsOfFile: envPath, encoding: .utf8) else { return "" }
        for line in text.split(separator: "\n") {
            let parts = line.split(separator: "=", maxSplits: 1)
            if parts.count == 2 && parts[0].trimmingCharacters(in: .whitespaces) == key {
                return String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return ""
    }

    func discordToken() -> String { envValue("DISCORD_TOKEN") }
    func announcementsChannelId() -> String { envValue("ANNOUNCEMENTS_CHANNEL_ID") }
    func changelogChannelId() -> String {
        let v = envValue("CHANGELOG_CHANNEL_ID")
        return v.isEmpty ? announcementsChannelId() : v
    }
    func channelId() -> String { announcementsChannelId() }
    func githubRepo() -> String {
        let v = envValue("GITHUB_REPO")
        return v.isEmpty ? "JustEroDeveloper/eAI" : v
    }

    func start() {
        guard process == nil || process?.isRunning == false else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: pythonPath)
        p.arguments = [botPath]
        p.currentDirectoryURL = URL(fileURLWithPath: (botPath as NSString).deletingLastPathComponent)
        var env = ProcessInfo.processInfo.environment
        let proxy = "http://127.0.0.1:10810"
        env["HTTPS_PROXY"] = proxy
        env["https_proxy"] = proxy
        env["HTTP_PROXY"] = proxy
        env["http_proxy"] = proxy
        p.environment = env
        if !FileManager.default.fileExists(atPath: logPath) {
            FileManager.default.createFile(atPath: logPath, contents: nil)
        }
        let handle = FileHandle(forWritingAtPath: logPath)
        handle?.seekToEndOfFile()
        p.standardOutput = handle
        p.standardError = handle
        do {
            try p.run()
            process = p
            updateMenu()
        } catch {
            showAlert("Failed to start bot: \(error.localizedDescription)")
        }
    }

    func stop() {
        process?.terminate()
        process = nil
        updateMenu()
    }

    func restart() {
        stop()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.start() }
    }

    func isRunning() -> Bool { process?.isRunning == true }

    func updateMenu() {
        let running = isRunning()
        startItem.isEnabled = !running
        stopItem.isEnabled = running
        restartItem.isEnabled = running
        statusItem.button?.title = running ? "🤖✅" : "🤖⛔"
    }

    func viewLogs() { NSWorkspace.shared.open(URL(fileURLWithPath: logPath)) }
    func openBotFolder() { NSWorkspace.shared.open(URL(fileURLWithPath: (botPath as NSString).deletingLastPathComponent)) }

    func toggleAutoStart() {
        if FileManager.default.fileExists(atPath: plistPath) {
            try? FileManager.default.removeItem(atPath: plistPath)
        } else {
            let plist = """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
                <key>Label</key>
                <string>com.eai.discordbot</string>
                <key>ProgramArguments</key>
                <array>
                    <string>\(appPath)/Contents/MacOS/eai-discord-bot</string>
                </array>
                <key>RunAtLoad</key>
                <true/>
                <key>EnvironmentVariables</key>
                <dict>
                    <key>HTTPS_PROXY</key>
                    <string>http://127.0.0.1:10810</string>
                    <key>https_proxy</key>
                    <string>http://127.0.0.1:10810</string>
                </dict>
            </dict>
            </plist>
            """
            try? plist.write(toFile: plistPath, atomically: true, encoding: .utf8)
        }
        updateAutoStartState()
    }

    func updateAutoStartState() {
        autoStartItem.state = FileManager.default.fileExists(atPath: plistPath) ? .on : .off
    }

    func showAlert(_ text: String) {
        let alert = NSAlert()
        alert.messageText = "eAI Discord Bot"
        alert.informativeText = text
        alert.runModal()
    }

    func postDiscord(embed: [String: Any], channelOverride: String = "", completion: @escaping (Bool) -> Void) {
        let token = discordToken()
        let channel = channelOverride.isEmpty ? channelId() : channelOverride
        guard !token.isEmpty, !channel.isEmpty else {
            showAlert("Set DISCORD_TOKEN and ANNOUNCEMENTS_CHANNEL_ID in .env")
            completion(false)
            return
        }
        let url = URL(string: "https://discord.com/api/v10/channels/\(channel)/messages")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bot \(token)", forHTTPHeaderField: "Authorization")
        let body: [String: Any] = ["embeds": [embed]]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        let task = URLSession.shared.dataTask(with: req) { _, resp, err in
            let ok = (resp as? HTTPURLResponse)?.statusCode == 200 || (resp as? HTTPURLResponse)?.statusCode == 201
            DispatchQueue.main.async { completion(ok && err == nil) }
        }
        task.resume()
    }

    func fetchLatestRelease(completion: @escaping (String, String) -> Void) {
        let url = URL(string: "https://api.github.com/repos/\(githubRepo())/releases/latest")!
        var req = URLRequest(url: url)
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        let task = URLSession.shared.dataTask(with: req) { data, _, _ in
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                DispatchQueue.main.async { completion("Latest Release", "Could not fetch release.") }
                return
            }
            let title = (json["name"] as? String) ?? (json["tag_name"] as? String) ?? "Latest Release"
            let body = (json["body"] as? String) ?? "No release notes."
            let link = (json["html_url"] as? String) ?? ""
            let text = "\(body)\n\n\(link)"
            DispatchQueue.main.async { completion(title, text) }
        }
        task.resume()
    }

    @objc func startAction() { start() }
    @objc func stopAction() { stop() }
    @objc func restartAction() { restart() }
    @objc func viewLogsAction() { viewLogs() }
    @objc func openFolderAction() { openBotFolder() }
    @objc func toggleAutoStartAction() { toggleAutoStart() }
    @objc func postChangelogAction() {
        fetchLatestRelease { title, body in
            let embed: [String: Any] = [
                "title": "📢 \(title)",
                "description": String(body.prefix(4000)),
                "color": 0x57F287
            ]
            self.postDiscord(embed: embed, channelOverride: self.changelogChannelId()) { ok in
                if !ok { self.showAlert("Failed to post changelog. Check .env token/channel.") }
            }
        }
    }
    @objc func postAnnouncementAction() {
        let alert = NSAlert()
        alert.messageText = "Post Announcement"
        let titleField = NSTextField(string: "")
        titleField.placeholderString = "Title"
        let messageField = NSTextField(string: "")
        messageField.placeholderString = "Message"
        let stack = NSStackView(views: [titleField, messageField])
        stack.orientation = .vertical
        stack.spacing = 8
        stack.frame = NSRect(x: 0, y: 0, width: 300, height: 60)
        titleField.frame = NSRect(x: 0, y: 32, width: 300, height: 22)
        messageField.frame = NSRect(x: 0, y: 0, width: 300, height: 22)
        alert.accessoryView = stack
        if alert.runModal() == .alertFirstButtonReturn {
            let title = titleField.stringValue
            let message = messageField.stringValue
            guard !title.isEmpty else { return }
            let embed: [String: Any] = [
                "title": title,
                "description": String(message.prefix(4000)),
                "color": 0xFEE75C
            ]
            postDiscord(embed: embed) { ok in
                if !ok { self.showAlert("Failed to post announcement. Check .env token/channel.") }
            }
        }
    }
    @objc func quitAction() { stop(); NSApp.terminate(nil) }

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "🤖"

        let menu = NSMenu()
        startItem = menu.addItem(withTitle: "Start Bot", action: #selector(startAction), keyEquivalent: "")
        stopItem = menu.addItem(withTitle: "Stop Bot", action: #selector(stopAction), keyEquivalent: "")
        restartItem = menu.addItem(withTitle: "Restart Bot", action: #selector(restartAction), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Post Latest Changelog", action: #selector(postChangelogAction), keyEquivalent: "")
        menu.addItem(withTitle: "Post Announcement...", action: #selector(postAnnouncementAction), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "View Logs", action: #selector(viewLogsAction), keyEquivalent: "")
        menu.addItem(withTitle: "Open Bot Folder", action: #selector(openFolderAction), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        autoStartItem = menu.addItem(withTitle: "Start at Login", action: #selector(toggleAutoStartAction), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Quit", action: #selector(quitAction), keyEquivalent: "q")
        for item in menu.items { item.target = self }
        statusItem.menu = menu

        updateAutoStartState()
        updateMenu()

        // Start bot automatically when controller opens
        start()
    }
}

let app = NSApplication.shared
let delegate = BotController()
app.delegate = delegate
app.run()