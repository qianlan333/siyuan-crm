import { selectEntityInViewState, updateWorkspaceViewState } from "./workspace_view_state.js";
function navigableLanes(lanes) {
    return lanes.filter((lane) => lane.isVisible && !lane.isCollapsed && lane.cards.length > 0);
}
function currentLaneIndex(lanes, viewState) {
    const index = lanes.findIndex((lane) => lane.id === viewState.focusedCanvasLaneId);
    return index >= 0 ? index : 0;
}
function currentCardIndex(lane, viewState) {
    const index = lane.cards.findIndex((card) => card.detailId === viewState.focusedCanvasCardId);
    return index >= 0 ? index : 0;
}
function clampIndex(index, length) {
    if (length <= 0)
        return 0;
    return Math.min(Math.max(index, 0), length - 1);
}
function focusCard(viewState, laneId, card) {
    return selectEntityInViewState(updateWorkspaceViewState(viewState, {
        focusedCanvasLaneId: laneId,
        focusedCanvasCardId: card.detailId
    }), card.entityType, card.detailId);
}
export function moveWorkspaceCanvasSelection(lanes, viewState, key) {
    if (key === "Escape") {
        return updateWorkspaceViewState(viewState, { panelMode: "summary" });
    }
    const visible = navigableLanes(lanes);
    if (visible.length === 0)
        return updateWorkspaceViewState(viewState, { panelMode: "summary" });
    const laneIndex = currentLaneIndex(visible, viewState);
    const lane = visible[laneIndex];
    const cardIndex = currentCardIndex(lane, viewState);
    if (key === "Enter" || key === " ") {
        return focusCard(viewState, lane.id, lane.cards[cardIndex]);
    }
    if (key === "ArrowUp" || key === "ArrowDown") {
        const direction = key === "ArrowUp" ? -1 : 1;
        const nextIndex = clampIndex(cardIndex + direction, lane.cards.length);
        return focusCard(viewState, lane.id, lane.cards[nextIndex]);
    }
    if (key === "ArrowLeft" || key === "ArrowRight") {
        const direction = key === "ArrowLeft" ? -1 : 1;
        const nextLaneIndex = clampIndex(laneIndex + direction, visible.length);
        const nextLane = visible[nextLaneIndex];
        const nextCard = nextLane.cards[clampIndex(cardIndex, nextLane.cards.length)];
        return focusCard(viewState, nextLane.id, nextCard);
    }
    return viewState;
}
export function keyboardHintText() {
    return "Keyboard preview: Arrow keys move local detail selection, Enter opens detail, Space toggles bundle selection, Escape returns to summary. No task is executed.";
}
