from dataclasses import dataclass
from typing import Any
import re


@dataclass
class ToolCall:
    """Represents a tool call proposed by the LLM."""

    name: str
    input: dict[str, Any]
    id: str


# =============================================================================
# Role-based DATA access (hard enforcement)
# =============================================================================
# Tables/record types each role may touch via SuiteQL / record / metadata tools.
# "*" means unrestricted. Names are matched case-insensitively as whole words.
ROLE_TABLE_ACCESS: dict[str, list[str]] = {
    "admin": ["*"],
    "finance": [
        "transaction", "transactionline", "transactionaccountingline",
        "invoice", "creditmemo", "vendorbill", "vendorcredit",
        "customer", "vendor", "contact", "entity",
        "customerpayment", "vendorpayment", "payment", "deposit",
        "account", "accountingperiod", "accountingbook", "currency",
        "department", "subsidiary", "classification", "location",
        "journalentry", "expensereport", "budget", "budgets",
    ],
    "inventory": [
        "item", "inventoryitem", "noninventoryitem", "assemblyitem",
        "serviceitem", "kititem", "inventorybalance", "inventorynumber",
        "inventorystatus", "purchaseorder", "salesorder",
        "location", "bin", "transferorder", "itemfulfillment",
        "itemreceipt", "vendor", "inventoryadjustment", "inventorycount",
    ],
}


class GuardrailEngine:
    """
    Validates tool calls against:
      1. Role-based tool permission (is the tool allowed for this role?)
      2. Role-based DATA access — for data tools, the table/record type the call
         touches must be within the role's allowed set.
    """

    # Tools whose arguments reference NetSuite tables/record types
    _SUITEQL_TOOLS = {"ns_runCustomSuiteQL"}
    _RECORDTYPE_TOOLS = {"ns_getSuiteQLMetadata", "ns_getRecord", "ns_getRecordTypeMetadata"}

    def __init__(self, allowed_tools: list[str], user_role: str = "admin"):
        self.allowed_tools = allowed_tools
        self.user_role = user_role
        self.allowed_tables = [t.lower() for t in ROLE_TABLE_ACCESS.get(user_role, [])]

    def validate(self, tool_call: ToolCall) -> tuple[bool, str | None]:
        # Check 1: tool permission
        if tool_call.name not in self.allowed_tools:
            return (
                False,
                f"Tool '{tool_call.name}' is not permitted for your role '{self.user_role}'.",
            )

        # Admin (or wildcard) bypasses data-scope checks
        if "*" in self.allowed_tables:
            return True, None

        # Check 2a: SuiteQL query — inspect referenced tables
        if tool_call.name in self._SUITEQL_TOOLS:
            query = str(tool_call.input.get("query", ""))
            allowed, denied = self._check_query_tables(query)
            if not allowed:
                return (
                    False,
                    f"Access denied: your role '{self.user_role}' cannot query the "
                    f"'{denied}' table. It is outside your data access scope.",
                )

        # Check 2b: record-type tools — inspect the recordType argument
        if tool_call.name in self._RECORDTYPE_TOOLS:
            record_type = str(
                tool_call.input.get("recordType", "")
                or tool_call.input.get("type", "")
            ).lower()
            if record_type and not self._is_table_allowed(record_type):
                return (
                    False,
                    f"Access denied: your role '{self.user_role}' cannot access the "
                    f"'{record_type}' record type. It is outside your data access scope.",
                )

        return True, None

    # ─── helpers ──────────────────────────────────────────────────────────────

    def _check_query_tables(self, query: str) -> tuple[bool, str | None]:
        for table in self._extract_tables(query):
            if not self._is_table_allowed(table):
                return False, table
        return True, None

    def _is_table_allowed(self, table: str) -> bool:
        return table.lower() in self.allowed_tables

    def _extract_tables(self, query: str) -> list[str]:
        """Extract table names following FROM / JOIN in a SuiteQL query."""
        tables = []
        for m in re.findall(r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", query, re.IGNORECASE):
            if m.upper() not in (
                "SELECT", "WHERE", "ORDER", "GROUP", "HAVING", "LIMIT", "FETCH", "ON", "AS",
            ):
                tables.append(m.lower())
        return tables
