import { SkeletonRows } from "../../../components/feedback/Skeleton.jsx";
import StepDetailPane from "../components/StepDetailPane.jsx";
import StepModal from "../components/StepModal.jsx";
import StepRow from "../components/StepRow.jsx";
import useStepLibrary from "../hooks/useStepLibrary.js";
import { filterSteps } from "../lib/steps.js";

/** Step Library: reusable steps, their usage, and the create / edit dialog. */
export default function StepLibraryPage() {
  const lib = useStepLibrary();
  const visible = filterSteps(lib.steps, lib.filters);
  const selected = lib.steps.find((s) => s.id === lib.selectedId) || null;
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
                className="
                  inline-flex min-h-[24px] items-center justify-center
                  rounded-md border border-slate-700/80
                  bg-slate-900/70 px-2
                  text-[11px] font-semibold text-slate-400
                "
              >
                {lib.status === "ready" || lib.steps.length ? `(${lib.steps.length})` : ""}
              </span>
            </div>

            <p className="mt-2 max-w-[760px] text-[12.5px] leading-5 text-slate-500">
              Reusable test steps shared across your test cases. Update a step
              once and every linked test case stays consistent.
            </p>
          </div>

          <button
            type="button"
            onClick={lib.openCreate}
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
                  value={lib.filters.q}
                  onChange={(e) => lib.setFilters({ q: e.target.value })}
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
                value={lib.filters.type}
                onChange={(e) => lib.setFilters({ type: e.target.value })}
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
                value={lib.filters.usage}
                onChange={(e) => lib.setFilters({ usage: e.target.value })}
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
              {/* The id stays: the guided tour points at the list. */}
              <div id="s-list-body" role="listbox" aria-label="Library steps">
                {lib.status === "loading" && (
                  <SkeletonRows count={8} label="Loading step library" />
                )}
                {lib.status === "error" && (
                  <div className="mt-2 p-[18px] text-[12.5px] text-red">
                    Couldn&apos;t load steps. {lib.error}
                  </div>
                )}
                {lib.status === "ready" &&
                  (visible.length ? (
                    visible.map((s) => (
                      <StepRow
                        key={s.id}
                        step={s}
                        selected={lib.selectedId === s.id}
                        onSelect={lib.selectRow}
                        onEdit={lib.openEdit}
                        onDelete={lib.remove}
                      />
                    ))
                  ) : (
                    <div className="flex min-h-[300px] flex-col items-center justify-center gap-[7px] text-center">
                      <div className="mb-1 flex h-[38px] w-[38px] items-center justify-center rounded-[9px] border border-solid border-[#243244] bg-[#101923] text-[#64748b]">
                        <svg
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                          className="h-[17px] w-[17px] fill-none stroke-current [stroke-linecap:round] [stroke-linejoin:round] [stroke-width:1.7]"
                        >
                          <circle cx="11" cy="11" r="7" />
                          <path d="m20 20-4-4" />
                        </svg>
                      </div>
                      <strong className="text-[12px] font-semibold text-[#aeb9c7]">No matching steps</strong>
                      <span className="text-[11px] text-[#5e6d81]">Try changing your search or filters.</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {selected && (
            <StepDetailPane
              step={selected}
              detail={lib.detail}
              onClose={lib.closeDetails}
              onOpenCase={lib.openCase}
            />
          )}
        </div>
      </div>
      <StepModal
        modal={lib.modal}
        setField={lib.setModalField}
        onClose={lib.closeModal}
        onSave={lib.save}
      />
    </section>
  );
}