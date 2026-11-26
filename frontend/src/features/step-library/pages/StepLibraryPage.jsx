/**
 * StepLibraryPage
 *
 * React-owned shell for Step Library.
 * Existing data loading, filtering, editing and deleting remain handled
 * by the compatibility controller.
 */
export default function StepLibraryPage() {
  return (
    <section
      id="view-steps"
      className="view"
      hidden
    >
      <div className="mx-auto w-full max-w-[1600px]  py-0">
        {/* =====================================================
            PAGE HEADER
        ====================================================== */}
        <div className="mb-6 flex items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-600">
              Test Management
            </div>

            <div className="flex items-center gap-3">
              <h1 className="m-0 text-[24px] font-semibold tracking-[-0.025em] text-slate-100">
                Step Library
              </h1>

              <span
                id="s-count"
                className="
                  inline-flex min-h-[24px] items-center justify-center
                  rounded-md border border-slate-700/80
                  bg-slate-900/70 px-2
                  text-[11px] font-semibold text-slate-400
                "
              />
            </div>

            <p className="mt-2 max-w-[760px] text-[12.5px] leading-5 text-slate-500">
              Reusable test steps shared across your test cases. Update a step
              once and every linked test case stays consistent.
            </p>
          </div>

          <button
            id="s-new"
            type="button"
            className="
              go
              !m-0 !inline-flex !h-10
              shrink-0 !items-center !justify-center !gap-2
              !rounded-lg !border-0
              !bg-cyan-500 !px-4
              !text-[12.5px] !font-semibold text-white
              transition-all duration-150
              hover:!-translate-y-px hover:!bg-cyan-400
              hover:!shadow-[0_8px_20px_rgba(6,182,212,0.16)]
              focus:!outline-none
              focus:!ring-2
              focus:!ring-cyan-400/25
            "
          >
            <svg
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>

            <span>New step</span>
          </button>
        </div>

        {/* =====================================================
            FILTER TOOLBAR
        ====================================================== */}
        <div
          className="
            mb-4
            rounded-xl border border-slate-800
            bg-[#0D151F]
            p-4
          "
        >
          <div className="grid grid-cols-[minmax(260px,1fr)_180px_180px] items-end gap-3 max-[900px]:grid-cols-2 max-[640px]:grid-cols-1">
            {/* Search */}
            <div className="min-w-0 max-[900px]:col-span-2 max-[640px]:col-span-1">
              <label
                htmlFor="s-search"
                className="mb-1.5 block text-[11px] font-medium text-slate-500"
              >
                Search
              </label>

              <div className="relative">
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600"
                  aria-hidden="true"
                >
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-4-4" />
                </svg>

                <input
                  type="text"
                  id="s-search"
                  placeholder="Search by action or expected result..."
                  className="
                    !m-0 !h-10 !w-full
                    !rounded-lg !border !border-slate-700/80
                    !bg-[#09111A]
                    !py-0 !pl-9 !pr-3
                    !text-[12.5px] !text-slate-200
                    !outline-none
                    transition-all
                    placeholder:!text-slate-600
                    hover:!border-slate-600
                    focus:!border-cyan-500/70
                    focus:!ring-2
                    focus:!ring-cyan-500/10
                  "
                />
              </div>
            </div>

            {/* Type */}
            <div>
              <label
                htmlFor="s-filter-type"
                className="mb-1.5 block text-[11px] font-medium text-slate-500"
              >
                Step type
              </label>

              <select
                id="s-filter-type"
                className="
                  !m-0 !h-10 !w-full
                  !rounded-lg !border !border-slate-700/80
                  !bg-[#09111A]
                  !px-3 !py-0
                  !text-[12.5px] !text-slate-300
                  !outline-none
                  transition-all
                  hover:!border-slate-600
                  focus:!border-cyan-500/70
                  focus:!ring-2
                  focus:!ring-cyan-500/10
                "
                aria-label="Filter by type"
              >
                <option value="">All types</option>
                <option value="Given">Given</option>
                <option value="When">When</option>
                <option value="Then">Then</option>
                <option value="And">And / But</option>
                <option value="Other">Other / Action</option>
              </select>
            </div>

            {/* Usage */}
            <div>
              <label
                htmlFor="s-filter-usage"
                className="mb-1.5 block text-[11px] font-medium text-slate-500"
              >
                Usage
              </label>

              <select
                id="s-filter-usage"
                className="
                  !m-0 !h-10 !w-full
                  !rounded-lg !border !border-slate-700/80
                  !bg-[#09111A]
                  !px-3 !py-0
                  !text-[12.5px] !text-slate-300
                  !outline-none
                  transition-all
                  hover:!border-slate-600
                  focus:!border-cyan-500/70
                  focus:!ring-2
                  focus:!ring-cyan-500/10
                "
                aria-label="Filter by Usage"
              >
                <option value="">All usage</option>
                <option value="used">Used steps</option>
                <option value="unused">Unused steps</option>
              </select>
            </div>
          </div>
        </div>

        {/* =====================================================
            CONTENT
        ====================================================== */}
        <div className="flex min-h-[620px] items-stretch gap-4">
          {/* STEP LIST */}
          <div
            className="
              min-w-0 flex-1
              overflow-hidden
              rounded-xl
              border border-slate-800
              bg-[#0A121C]
            "
          >
            {/* List heading */}
            <div
              className="
                flex h-12 items-center justify-between
                border-b border-slate-800
                px-5
              "
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                Library steps
              </div>

              <div className="text-[10.5px] text-slate-600">
                Select a row to view usage
              </div>
            </div>

            <div className="max-h-[650px] min-h-[560px] overflow-y-auto">
              <div id="s-list-body">
                {/* Loaded dynamically */}
              </div>
            </div>
          </div>

          {/* =====================================================
              DETAIL PANEL
          ====================================================== */}
          <aside
            id="s-detail-pane"
            style={{ display: "none" }}
            className="
              w-[360px] shrink-0
              flex-col
              overflow-hidden
              rounded-xl
              border border-slate-800
              bg-[#0D151F]
              max-[1100px]:w-[320px]
            "
          >
            {/* Drawer header */}
            <div
              className="
                flex min-h-[60px] items-center justify-between
                border-b border-slate-800
                px-5
              "
            >
              <div>
                <div className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-600">
                  Selected step
                </div>

                <h3 className="mt-0.5 text-[14px] font-semibold text-slate-200">
                  Step details
                </h3>
              </div>

              <button
                className="
                  ghost
                  !flex !h-8 !w-8
                  !items-center !justify-center
                  !rounded-lg
                  !border !border-transparent
                  !bg-transparent
                  !p-0
                  !text-slate-500
                  transition-all
                  hover:!border-slate-700
                  hover:!bg-slate-800
                  hover:!text-slate-200
                "
                id="s-detail-close"
                type="button"
                title="Close details"
                aria-label="Close step details"
              >
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                >
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>

            {/* Detail content */}
            <div className="flex flex-1 flex-col gap-6 p-5">
              {/* Type */}
              <div>
                <span className="block text-[9.5px] font-semibold uppercase tracking-[0.1em] text-slate-600">
                  Type
                </span>

                <div
                  id="s-detail-type"
                  className="mt-2"
                />
              </div>

              {/* Action */}
              <div>
                <span className="block text-[9.5px] font-semibold uppercase tracking-[0.1em] text-slate-600">
                  Action / Description
                </span>

                <div
                  id="s-detail-action"
                  className="
                    mt-2 break-words
                    text-[13px] font-medium
                    leading-5 text-slate-200
                  "
                />
              </div>

              {/* Expected result */}
              <div>
                <span className="block text-[9.5px] font-semibold uppercase tracking-[0.1em] text-slate-600">
                  Expected result
                </span>

                <div
                  id="s-detail-expected"
                  className="
                    mt-2 break-words
                    text-[12px] leading-5
                    text-slate-400
                  "
                />
              </div>

              {/* Used cases */}
              <div className="border-t border-slate-800 pt-5">
                <div
                  id="s-detail-cases-title"
                  className="
                    flex items-center gap-2
                    text-[11px] font-semibold
                    text-slate-400
                  "
                >
                  Used in cases (0)
                </div>

                <div
                  id="s-detail-cases-list"
                  className="
                    mt-3 flex max-h-[320px]
                    flex-col gap-2
                    overflow-y-auto
                  "
                >
                  {/* Loaded dynamically */}
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}