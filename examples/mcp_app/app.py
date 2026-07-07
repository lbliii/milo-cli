"""Minimal MCP Apps resource and linked tool using only Milo's public API."""

from __future__ import annotations

from milo import CLI, MCPAppResourceMeta, MCPAppToolMeta

cli = CLI(name="weather-app", description="Weather tool with an optional MCP App view")

FORECAST_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Weather forecast</title>
    <style>
      :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
      body { margin: 0; padding: 1rem; }
      main { display: grid; gap: 0.75rem; max-width: 28rem; }
      form { display: flex; gap: 0.5rem; }
      input { flex: 1; min-width: 0; padding: 0.5rem; }
      button { padding: 0.5rem 0.75rem; }
      output { font-size: 1.2rem; font-weight: 600; }
      #status { opacity: 0.75; }
    </style>
  </head>
  <body>
    <main>
      <h1>Weather forecast</h1>
      <form id="forecast-form">
        <label for="city">City</label>
        <input id="city" name="city" value="Boston" autocomplete="off">
        <button id="refresh" type="submit" disabled>Refresh</button>
      </form>
      <output id="forecast" aria-live="polite">Waiting for a tool result…</output>
      <small id="status" aria-live="polite">Connecting to the MCP Apps host…</small>
    </main>
    <script>
      (() => {
        const pending = new Map();
        const city = document.querySelector("#city");
        const forecast = document.querySelector("#forecast");
        const refresh = document.querySelector("#refresh");
        const status = document.querySelector("#status");
        let nextId = 1;
        let toolName = "forecast";

        function post(message) {
          window.parent.postMessage({ jsonrpc: "2.0", ...message }, "*");
        }

        function request(method, params) {
          const id = nextId++;
          post({ id, method, params });
          return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => {
              pending.delete(id);
              reject(new Error(`${method} timed out`));
            }, 10000);
            pending.set(id, { resolve, reject, timer });
          });
        }

        function notify(method, params = {}) {
          post({ method, params });
        }

        function renderToolResult(result) {
          const data = result && result.structuredContent;
          if (!data || typeof data !== "object") {
            status.textContent = "The tool returned no structured forecast.";
            return;
          }
          city.value = typeof data.city === "string" ? data.city : city.value;
          forecast.textContent = `${data.city}: ${data.condition}, ${data.temperature_f}°F`;
          status.textContent = "Forecast updated.";
        }

        window.addEventListener("message", (event) => {
          if (event.source !== window.parent) return;
          const message = event.data;
          if (!message || message.jsonrpc !== "2.0") return;

          if (Object.hasOwn(message, "id") && pending.has(message.id)) {
            const entry = pending.get(message.id);
            pending.delete(message.id);
            window.clearTimeout(entry.timer);
            if (message.error) entry.reject(new Error(message.error.message || "Host error"));
            else entry.resolve(message.result);
            return;
          }

          if (message.method === "ui/notifications/tool-input") {
            const inputCity = message.params && message.params.arguments?.city;
            if (typeof inputCity === "string") city.value = inputCity;
          } else if (message.method === "ui/notifications/tool-result") {
            renderToolResult(message.params);
          }
        });

        document.querySelector("#forecast-form").addEventListener("submit", async (event) => {
          event.preventDefault();
          if (refresh.disabled) return;
          status.textContent = "Requesting a fresh forecast…";
          try {
            const result = await request("tools/call", {
              name: toolName,
              arguments: { city: city.value },
            });
            renderToolResult(result);
          } catch (error) {
            status.textContent = error instanceof Error ? error.message : String(error);
          }
        });

        request("ui/initialize", {
          protocolVersion: "2026-01-26",
          appInfo: { name: "Milo weather view", version: "1.0.0" },
          appCapabilities: {},
        }).then((result) => {
          toolName = result?.hostContext?.toolInfo?.tool?.name || toolName;
          refresh.disabled = !result?.hostCapabilities?.serverTools;
          notify("ui/notifications/initialized");
          status.textContent = refresh.disabled
            ? "Connected. This host does not proxy View tool calls."
            : "Connected. Change the city to call the tool again.";
        }).catch((error) => {
          status.textContent = error instanceof Error ? error.message : String(error);
        });
      })();
    </script>
  </body>
</html>"""


@cli.ui_resource(
    "ui://weather-app/forecast",
    name="Weather forecast",
    description="Static HTML shell for structured forecast results",
    meta=MCPAppResourceMeta(prefers_border=True),
)
def forecast_view() -> str:
    """Return the predeclared HTML5 document fetched by an MCP Apps host."""
    return FORECAST_HTML


@cli.command(
    "forecast",
    description="Get a weather forecast",
    annotations={"readOnlyHint": True},
    ui=MCPAppToolMeta("ui://weather-app/forecast"),
)
def forecast(city: str = "Boston") -> dict[str, str | int]:
    """Return structured data for text-only and MCP Apps hosts.

    Args:
        city: City to forecast.
    """
    return {"city": city, "condition": "sunny", "temperature_f": 72}


if __name__ == "__main__":
    cli.run()
