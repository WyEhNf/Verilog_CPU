"""Skip redundant priority only after caller-proven one-hot qualification."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


def edit(t,items):
    for width,events,name in items:
        old=f'rv32_frequency_event_select #(.WIDTH({width}),.EVENTS({events})) {name} ('
        new=f'rv32_frequency_event_select #(.WIDTH({width}),.EVENTS({events}),.PRIORITY(0)) {name} ('
        t=change(t,old,new)
    return t


def station(t):
    return edit(t,[('32','WAKE_WIDTH',n+'_selector') for n in ['first1','last1','first2','last2']])


def backend(t):
    return edit(t,[('32','RS_ENTRIES','immediate_selector'),
                   ('FEEDBACK_PACKET_WIDTH','BE_WIDTH','feedback_payload_selector'),
                   ('MDU_ISSUE_PAYLOAD_WIDTH','BE_WIDTH','mdu_payload_selector'),
                   ('BRANCH_CAPTURE_WIDTH','BE_WIDTH','branch_capture_selector'),
                   ('8','BE_WIDTH','history_selector')])


def store(t):
    return edit(t,[('STORE_PACKET_WIDTH','LSQ_ENTRIES','store_packet_selector'),
                   ('32','RS_ENTRIES','base_selector')])


if __name__=='__main__':
    prepare('BX_elide_onehot_rearbitration',ROOT/'BW_frontend_state_and_dispatch_queries',{
        'rtl/backend/rv32_reservation_station.v':station,
        'rtl/backend/rv32_backend_joint.v':backend,
        'rtl/backend/rv32_store_address_select.v':store,
    },'BW plus no second last-event prefix on eleven caller-proven one-hot selector declarations: first/last wake prefix grants, encoded-lane MDU/feedback grants, first branch-capture prefix and its history, encoded store/RS grants and shared immediate; retain last-event priority for all unproven/multiple row update cases; preserve every legal selection and duplicate-wake first/last policy; no new FF/cycles, no EDA')
