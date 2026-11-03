# StuntDouble integration scope

The StuntDouble change supports discovering remote MCP tools and running their
mocks locally. It contains the client transport, catalog importer, schema
preservation, documentation, and tests in this repository.

| Capability | StuntDouble behavior | Gateway prerequisite |
| --- | --- | --- |
| Streamable HTTP discovery | Connect to the exact endpoint with caller-supplied headers, negotiate a session, and read every tool page | A standard Streamable HTTP MCP endpoint; no gateway modification |
| Offline catalog import | Read the existing `GET /api/tool-catalog` endpoint and retain returned input schemas | The endpoint must include complete stored schemas |
| Local mock execution | Customize mirrored tools and run them through the existing LangGraph mock wrapper | No gateway or backend connection during mock execution |

SD uses the gateway's public HTTP interfaces. It does not import gateway modules,
provision gateway services, alter gateway permissions, or implement OAuth login.
Authentication headers remain the caller's responsibility.

## Separate upstream work

Evaluation against MCP Gateway Registry base revision
`f979d573d2679361972729da2fb8e86a94b02c83` identified the following follow-ups.
Any contribution for these belongs in a separate PR to that repository.

1. **Stored input schemas.** The registry can normalize a stored tool's schema to
   `schema`, while its catalog and virtual mapping fallback read other field names.
   An affected catalog entry contains `input_schema: {}`. SD cannot reconstruct
   information absent from the response, so it raises an actionable error before
   registering any mocks. Direct MCP discovery remains available when the backend
   is online. Offline import for affected entries needs an upstream schema fix.
2. **Tool discovery permissions.** A virtual gateway may advertise a tool to a
   caller whose invocation is denied. Filtering those names belongs to the
   gateway's authorization layer. SD consumes the returned discovery inventory;
   local mock execution does not verify gateway authorization.
3. **Hosted mock backend and deployment.** The optional FastMCP mock backend,
   gateway registration examples, and registry Compose profile are separate
   integration work. They are not dependencies of SD's client transport or local
   mock execution.

The tool discovery permission fix is independent of the stored-schema fix. A
gateway mock-backend proposal should also be reviewed independently from these
gateway bug fixes.

## Validation boundaries

The SD tests exercise real HTTP exchanges and official MCP SDK sessions against a
local protocol fixture. They cover authentication errors, redirects, pagination,
session cleanup, catalog validation, exact input schemas, and local mocked tool
execution. They run without a registry checkout or a gateway patch.

Successful tests against a gateway with local patches demonstrate the combined
system only. They do not establish that every gateway deployment already provides
complete catalog schemas or correct discovery authorization. SD's standalone
validation and the separate upstream changes must be reported independently.
