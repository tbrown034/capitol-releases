import * as d3 from "d3";

type AxisG = d3.Selection<SVGGElement, unknown, null, undefined>;

const GRID_STROKE = "#e5e5e5";
const TICK_TEXT = "#a3a3a3";
const TICK_FONT = 10;

// Dashed horizontal gridlines, axis line removed, muted tick labels.
export function drawYGrid(
  g: AxisG,
  y: d3.AxisScale<d3.NumberValue>,
  innerW: number,
  ticks = 4,
) {
  g.append("g")
    .call(d3.axisLeft(y).ticks(ticks).tickSize(-innerW))
    .call((sel) => sel.select(".domain").remove())
    .call((sel) =>
      sel
        .selectAll(".tick line")
        .attr("stroke", GRID_STROKE)
        .attr("stroke-dasharray", "2,2")
    )
    .call((sel) =>
      sel
        .selectAll(".tick text")
        .attr("fill", TICK_TEXT)
        .attr("font-size", TICK_FONT)
    );
}

// Time X-axis: domain + tick lines stripped, muted tick labels.
export function drawTimeAxis(
  g: AxisG,
  x: d3.AxisScale<Date>,
  innerH: number,
  format = "%b %Y",
  ticks = 6,
) {
  g.append("g")
    .attr("transform", `translate(0,${innerH})`)
    .call(
      d3
        .axisBottom(x)
        .ticks(ticks)
        .tickFormat((d) => d3.timeFormat(format)(d as Date)),
    )
    .call((sel) => sel.select(".domain").remove())
    .call((sel) => sel.selectAll(".tick line").remove())
    .call((sel) =>
      sel
        .selectAll(".tick text")
        .attr("fill", TICK_TEXT)
        .attr("font-size", TICK_FONT),
    );
}
