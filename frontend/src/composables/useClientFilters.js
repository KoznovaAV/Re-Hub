import { computed, ref } from "vue";
import { archiveCount, clientMetrics } from "../mock/data.js";

export function useClientFilters(clients, archiveGroup) {
  const search = ref("");
  const stage = ref("all");
  const tag = ref("all");
  const minShare = ref("0");
  const owner = ref("all");
  const includeMissing = ref(true);
  const sortKey = ref("name");
  const sortDir = ref("asc");

  const stages = computed(() => ["all", ...new Set(clients.value.map((item) => item.stage))]);
  const tags = computed(() => ["all", ...new Set(clients.value.flatMap((item) => item.tags))]);

  const filtered = computed(() => {
    const query = search.value.trim().toLowerCase();
    return clients.value
      .map((client) => ({ client, metrics: clientMetrics(client) }))
      .filter(({ client, metrics }) => {
        if (query) {
          const haystack = `${client.name} ${client.inn} ${client.externalId}`.toLowerCase();
          if (!haystack.includes(query)) return false;
        }
        if (archiveGroup.value !== "all" && !archiveCount(metrics, archiveGroup.value)) return false;
        if (stage.value !== "all" && client.stage !== stage.value) return false;
        if (tag.value !== "all" && !client.tags.includes(tag.value)) return false;
        if (minShare.value !== "0" && (metrics.share ?? 0) < Number(minShare.value)) return false;
        if (!includeMissing.value && metrics.missing) return false;
        if (owner.value === "free" && !metrics.free) return false;
        if (owner.value === "mine" && !client.owner) return false;
        return true;
      })
      .sort((a, b) => {
        const direction = sortDir.value === "asc" ? 1 : -1;
        if (sortKey.value === "code") return a.client.externalId.localeCompare(b.client.externalId) * direction;
        if (sortKey.value === "share") return ((a.metrics.share ?? -1) - (b.metrics.share ?? -1)) * direction;
        if (sortKey.value === "plan") return ((a.metrics.total ?? -1) - (b.metrics.total ?? -1)) * direction;
        if (sortKey.value === "transferred") return ((a.metrics.transferred ?? -1) - (b.metrics.transferred ?? -1)) * direction;
        if (sortKey.value === "percent") return ((a.metrics.transferredPercent ?? -1) - (b.metrics.transferredPercent ?? -1)) * direction;
        if (sortKey.value === "delta") return ((a.metrics.delta ?? 0) - (b.metrics.delta ?? 0)) * direction;
        if (sortKey.value === "unsent") return (a.metrics.unsent - b.metrics.unsent) * direction;
        if (sortKey.value === "stage") return a.client.stage.localeCompare(b.client.stage, "ru") * direction;
        if (sortKey.value === "owner") return a.metrics.ownerName.localeCompare(b.metrics.ownerName, "ru") * direction;
        if (sortKey.value === "promise") return String(a.client.promise ?? "").localeCompare(String(b.client.promise ?? "")) * direction;
        return a.client.name.localeCompare(b.client.name, "ru") * direction;
      });
  });

  function sortBy(key) {
    if (sortKey.value === key) sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
    else {
      sortKey.value = key;
      sortDir.value = "asc";
    }
  }

  function reset() {
    search.value = "";
    stage.value = "all";
    tag.value = "all";
    minShare.value = "0";
    owner.value = "all";
    includeMissing.value = true;
    sortKey.value = "name";
    sortDir.value = "asc";
  }

  return { search, stage, tag, minShare, owner, includeMissing, sortKey, sortDir, stages, tags, filtered, sortBy, reset };
}
