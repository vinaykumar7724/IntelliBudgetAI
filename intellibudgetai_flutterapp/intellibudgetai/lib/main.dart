import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

const kHomeUrl = 'https://intellibudgetai-production.up.railway.app/';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const IntelliBudgetApp());
}

class IntelliBudgetApp extends StatelessWidget {
  const IntelliBudgetApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'IntelliBudget AI',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF734F9A)),
        useMaterial3: true,
      ),
      home: const WebAppShell(),
    );
  }
}

class WebAppShell extends StatefulWidget {
  const WebAppShell({super.key});

  @override
  State<WebAppShell> createState() => _WebAppShellState();
}

class _WebAppShellState extends State<WebAppShell> {
  InAppWebViewController? _controller;
  double _progress = 0;
  late final PullToRefreshController _pullToRefreshController;
  String? _loadError;
  Uri? _lastTriedUrl;

  @override
  void initState() {
    super.initState();
    _requestPermissions();
    _pullToRefreshController = PullToRefreshController(
      onRefresh: () async {
        final c = _controller;
        if (c == null) {
          _pullToRefreshController.endRefreshing();
          return;
        }
        if (Platform.isAndroid) {
          await c.reload();
        } else if (Platform.isIOS) {
          final url = await c.getUrl();
          if (url != null) {
            await c.loadUrl(urlRequest: URLRequest(url: url));
          }
        }
      },
    );
  }

  Future<void> _requestPermissions() async {
    await [
      Permission.camera,
      Permission.microphone,
      Permission.locationWhenInUse,
    ].request();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 3)),
    );
  }

  Future<Directory> _downloadsDir() async {
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/downloads');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  String _sanitizeFilename(String input) {
    final cleaned = input.replaceAll(RegExp(r'[^a-zA-Z0-9._ -]'), '_').trim();
    return cleaned.isEmpty ? 'download' : cleaned;
  }

  String _ensurePdfExt(String filename, String url) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.pdf')) return filename;
    if (url.contains('/export/pdf') || url.contains('.pdf')) return '$filename.pdf';
    return filename;
  }

  bool _looksLikePdf(Uint8List bytes) {
    if (bytes.length < 4) return false;
    return bytes[0] == 0x25 && bytes[1] == 0x50 && bytes[2] == 0x44 && bytes[3] == 0x46; // %PDF
  }

  Future<Map<String, String>> _cookieHeaderForUrl(Uri uri) async {
    final cookies = await CookieManager.instance().getCookies(
      url: WebUri(uri.toString()),
    );
    if (cookies.isEmpty) return {};
    final cookie = cookies.map((c) => '${c.name}=${c.value}').join('; ');
    return {'Cookie': cookie};
  }

  Future<File> _downloadWithWebViewSession(DownloadStartRequest request) async {
    final urlStr = request.url.toString();
    final uri = Uri.parse(urlStr);

    final suggested = request.suggestedFilename ?? (uri.pathSegments.isNotEmpty ? uri.pathSegments.last : 'report');
    final filename = _ensurePdfExt(_sanitizeFilename(suggested), urlStr);

    final dir = await _downloadsDir();
    final file = File('${dir.path}/$filename');

    final cookieHdr = await _cookieHeaderForUrl(uri);
    final headers = <String, String>{
      ...cookieHdr,
    };

    final dio = Dio();
    final resp = await dio.get<List<int>>(
      urlStr,
      options: Options(
        responseType: ResponseType.bytes,
        followRedirects: true,
        receiveTimeout: const Duration(seconds: 60),
        headers: headers,
        validateStatus: (s) => s != null && s >= 200 && s < 400,
      ),
    );

    final bytes = Uint8List.fromList(resp.data ?? const <int>[]);
    if (bytes.isEmpty) {
      throw Exception('Empty download');
    }

    // If we got HTML instead of PDF, it’s usually a login page/redirect.
    final contentType = (resp.headers.value('content-type') ?? '').toLowerCase();
    if (filename.toLowerCase().endsWith('.pdf')) {
      final okByHeader = contentType.contains('application/pdf');
      final okByMagic = _looksLikePdf(bytes);
      if (!okByHeader && !okByMagic) {
        throw Exception('Downloaded content is not a PDF (likely requires login).');
      }
    }

    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('IntelliBudget AI'),
        bottom: _progress < 1
            ? PreferredSize(
                preferredSize: const Size.fromHeight(2),
                child: LinearProgressIndicator(value: _progress),
              )
            : null,
        actions: [
          IconButton(
            tooltip: 'Reload',
            onPressed: () => _controller?.reload(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: Stack(
          children: [
            InAppWebView(
              initialUrlRequest: URLRequest(url: WebUri(kHomeUrl)),
              pullToRefreshController: _pullToRefreshController,
              initialSettings: InAppWebViewSettings(
                javaScriptEnabled: true,
                mediaPlaybackRequiresUserGesture: false,
                allowsInlineMediaPlayback: true,
                useOnDownloadStart: true,
                useShouldOverrideUrlLoading: true,
                geolocationEnabled: true,
              ),
              onWebViewCreated: (controller) => _controller = controller,
              // Required when useShouldOverrideUrlLoading is true; without this,
              // initial navigation can be blocked and the screen stays blank.
              shouldOverrideUrlLoading: (controller, navigationAction) async {
                final uri = navigationAction.request.url;
                if (uri == null) return NavigationActionPolicy.ALLOW;
                _lastTriedUrl = Uri.tryParse(uri.toString());
                final scheme = uri.scheme.toLowerCase();
                if (scheme == 'http' || scheme == 'https') {
                  return NavigationActionPolicy.ALLOW;
                }
                return NavigationActionPolicy.CANCEL;
              },
              onLoadStart: (controller, url) {
                setState(() {
                  _loadError = null;
                  _lastTriedUrl = url != null ? Uri.tryParse(url.toString()) : _lastTriedUrl;
                });
              },
              onProgressChanged: (controller, progress) {
                setState(() => _progress = progress / 100.0);
                if (progress == 100) _pullToRefreshController.endRefreshing();
              },
              onLoadStop: (controller, url) {
                _pullToRefreshController.endRefreshing();
                setState(() => _loadError = null);
              },
              onReceivedError: (controller, request, error) {
                _pullToRefreshController.endRefreshing();
                setState(() {
                  _lastTriedUrl = Uri.tryParse(request.url.toString());
                  _loadError = 'Network error (${error.type}): ${error.description}';
                });
              },
              onReceivedHttpError: (controller, request, errorResponse) {
                _pullToRefreshController.endRefreshing();
                setState(() {
                  _lastTriedUrl = Uri.tryParse(request.url.toString());
                  _loadError =
                      'HTTP error (${errorResponse.statusCode}): ${errorResponse.reasonPhrase ?? 'Unknown'}';
                });
              },

              // Camera/Mic prompts from within the website.
              onPermissionRequest: (controller, request) async {
                return PermissionResponse(
                  resources: request.resources,
                  action: PermissionResponseAction.GRANT,
                );
              },

              onGeolocationPermissionsShowPrompt: (controller, origin) async {
                return GeolocationPermissionShowPromptResponse(
                  origin: origin,
                  allow: true,
                  retain: true,
                );
              },

              onDownloadStartRequest: (controller, request) async {
                try {
                  _snack('Downloading…');
                  final file = await _downloadWithWebViewSession(request);
                  _snack('Saved: ${file.path.split('/').last}');
                  await OpenFilex.open(file.path);
                } catch (e) {
                  _snack('Cannot open download: $e');
                }
              },
            ),
            if (_loadError != null)
              Positioned.fill(
                child: Container(
                  color: Theme.of(context).colorScheme.surface,
                  alignment: Alignment.center,
                  padding: const EdgeInsets.all(16),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Cannot load IntelliBudget AI',
                              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'This usually happens when a Wi‑Fi network blocks the site (DNS/firewall/captive portal) or intercepts HTTPS.',
                              style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                            ),
                            const SizedBox(height: 10),
                            if (_lastTriedUrl != null)
                              Text(
                                'URL: ${_lastTriedUrl.toString()}',
                                style: const TextStyle(fontSize: 12),
                              ),
                            const SizedBox(height: 6),
                            Text(
                              _loadError!,
                              style: const TextStyle(fontSize: 12),
                            ),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 10,
                              runSpacing: 10,
                              children: [
                                FilledButton(
                                  onPressed: () => _controller?.reload(),
                                  child: const Text('Retry'),
                                ),
                                OutlinedButton(
                                  onPressed: () async {
                                    final url = _lastTriedUrl?.toString() ?? kHomeUrl;
                                    await InAppBrowser.openWithSystemBrowser(url: WebUri(url));
                                  },
                                  child: const Text('Open in browser'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
