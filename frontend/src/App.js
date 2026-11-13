import { computed, defineComponent, ref } from "vue";
import { store, clientMetrics, users } from "./mock/data.js";
import { pushToast, dismissToast, toasts } from "./composables/useToast.js";
import AppSidebar from "./components/AppSidebar.js";
import AppTopbar from "./components/AppTopbar.js";
import UiToastStack from "./components/UiToastStack.js";
import DashboardView from "./views/DashboardView.js";
import ClientsView from "./views/ClientsView.js";
import WorkView from "./views/WorkView.js";
import HistoryView from "./views/HistoryView.js";
import ClientCardView from "./views/ClientCardView.js";
import ImportView from "./views/ImportView.js";

export default defineComponent({
  name: "App",
  components: {
    AppSidebar,
    AppTopbar,
    UiToastStack,
    DashboardView,
    ClientsView,
    WorkView,
    HistoryView,
    ClientCardView,
    ImportView,
  },
  setup() {
    const view = ref("dashboard");
    const selectedId = ref("");
    const actor = ref("admin");
    const lastList = ref("clients");
    const archiveGroup = ref("all");

    const actionCount = computed(
      () =>
        store.clients.filter((client) => {
          const metrics = clientMetrics(client);
          return !metrics.missing && client.stage !== "Закрыт" && (metrics.needsRepeat || metrics.overdue);
        }).length,
    );

    const selectedClient = computed(() => store.clients.find((client) => client.id === selectedId.value) ?? null);

    function navigate(next, group) {
      if (next === "import" && actor.value !== "admin") {
        pushToast("Нет доступа", "Импорт доступен только администратору.", "warning");
        return;
      }
      if (["dashboard", "clients", "work", "history"].includes(next)) lastList.value = next;
      if (next === "clients" && group) archiveGroup.value = group;
      view.value = next;
      if (next !== "client") selectedId.value = "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function openClient(id) {
      selectedId.value = id;
      view.value = "client";
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function setActor(value) {
      actor.value = value;
      if (value !== "admin" && view.value === "import") view.value = "dashboard";
      pushToast("Пользователь переключён", `Текущая роль: ${users[value].name}.`, "info");
    }

    return {
      view,
      selectedId,
      actor,
      lastList,
      archiveGroup,
      actionCount,
      clientCount: computed(() => store.clients.length),
      selectedClient,
      navigate,
      openClient,
      setActor,
      toasts,
      dismissToast,
      store,
    };
  },
  template: `
    <div class="app">
      <AppSidebar
        :view="view"
        :actor="actor"
        :action-count="actionCount"
        :client-count="clientCount"
        @navigate="navigate($event, 'all')"
      />
      <div class="app__main">
        <AppTopbar
          :view="view"
          :client-name="selectedClient ? selectedClient.name : ''"
          :actor="actor"
          @update:actor="setActor"
          @navigate="navigate"
        />
        <DashboardView
          v-if="view === 'dashboard'"
          :clients="store.clients"
          :actor="actor"
          @open-client="openClient"
          @navigate="navigate"
        />
        <ClientsView
          v-else-if="view === 'clients'"
          v-model:archive-group="archiveGroup"
          :clients="store.clients"
          :actor="actor"
          @open-client="openClient"
          @navigate="navigate"
        />
        <WorkView
          v-else-if="view === 'work'"
          :clients="store.clients"
          :actor="actor"
          @open-client="openClient"
        />
        <HistoryView
          v-else-if="view === 'history'"
          :clients="store.clients"
          @open-client="openClient"
          @navigate="navigate"
        />
        <ClientCardView
          v-else-if="view === 'client'"
          :client-id="selectedId"
          :clients="store.clients"
          :actor="actor"
          @back="navigate(lastList)"
          @open-client="openClient"
        />
        <ImportView
          v-else-if="view === 'import'"
          :actor="actor"
          @navigate="navigate"
          @open-client="openClient"
        />
      </div>
      <UiToastStack :toasts="toasts" @dismiss="dismissToast" />
    </div>
  `,
});
