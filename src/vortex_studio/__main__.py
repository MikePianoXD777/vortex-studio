import sys

# El servidor MCP va antes que nada: sin Qt ni ventanas, para que Claude lo
# arranque al instante. Ver `mcp.py`.
if "--mcp" in sys.argv[1:]:
    from vortex_studio.mcp import main as mcp_main

    raise SystemExit(mcp_main())

from vortex_studio.app import main

raise SystemExit(main())
