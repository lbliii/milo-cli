"""Minimal MCP Apps resource and linked tool using only Milo's public API."""

from __future__ import annotations

from milo import CLI, MCPAppResourceMeta, MCPAppToolMeta

cli = CLI(name="weather-app", description="Weather tool with an optional MCP App view")


@cli.ui_resource(
    "ui://weather-app/forecast",
    name="Weather forecast",
    description="Static HTML shell for structured forecast results",
    meta=MCPAppResourceMeta(prefers_border=True),
)
def forecast_view() -> str:
    """Return the predeclared HTML5 document fetched by an MCP Apps host."""
    return """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Weather forecast</title></head>
  <body><main id="forecast">Forecast data arrives through the MCP Apps host.</main></body>
</html>"""


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
