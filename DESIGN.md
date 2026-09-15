# Spend interface

Spend is a personal statement ledger. Prioritize understandable financial amounts, category review, and traceability to imported statements. Never invent financial data for visual polish.

Use warm ivory (#f6f5f0), white paper surfaces, warm gray borders (#dfe2d9), dark ink (#25352c), and forest green (#27634c). Red is debit/error context; green is credit/success context. Always pair color with words or signs. Category colors are data identifiers, not text contrast guarantees.

Use local system fonts: Avenir Next/Segoe UI for controls and data, Iowan Old Style/Georgia for page titles. Enable tabular figures. No external font request is required.

Desktop uses a compact sidebar and bounded content. Below 768px navigation becomes a horizontal, keyboard accessible list. Mark the current route with aria-current. Keep a skip link, visible focus, 42px controls, and reduced motion support. Wide tables scroll within their own container.

Show loading placeholders until values arrive. Errors must be visible and recoverable. Empty screens explain the next useful action, with statement import as the primary path. Transfers and card repayments must not be presented as consumption: current debit/credit analytics are outflow/inflow, not adjusted spending/income. Limit notices identify partial result sets.

Verify overview, transaction filtering, category drilldown, and statement import at desktop and narrow mobile widths with synthetic data. Verify failure and empty states separately. Do not import demo rows into a user's real ledger to test the interface.
