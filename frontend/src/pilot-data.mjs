export const periods = ["2026Q2", "2026Q3"];

export function sample(group) {
  if (!["A", "B"].includes(group)) throw new RangeError("Unknown pilot group");
  const offset = group === "A" ? 0 : 30;
  return Array.from({length: 30}, (_, index) => {
    const number = offset + index + 1;
    const client = `PILOT-${String(number).padStart(2, "0")}`;
    return {
      client,
      periods: periods.map((period, k) => ({
        period, observed: !(index % 7 === 0 && k === 1),
        unsent: (index * 7 + k * 5) % 18,
        contacted: index % 4 === k,
        promise: index % 4 === k ? `2026-11-${String(10 + index % 15)}` : "",
      })),
      excluded: index % 6 === 0,
    };
  });
}

export function callList(rows, period, minimum) {
  return rows.filter(({excluded, periods: values}) => {
    const observation = values.find(item => item.period === period);
    return !excluded && observation?.observed && observation.unsent >= minimum && !observation.contacted;
  });
}
