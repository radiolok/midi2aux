// MIDI byte stream -> events {status, d1, d2}. Model: fpga/model/synthmodel/midi.py.
//   channel messages with running status; Note On vel 0 -> Note Off (8n kk 40);
//   1-data messages (Cn, Dn): d2 = 0;
//   System Realtime (F8..FF): emitted at once as {b, 0, 0}, running status kept;
//   System Common (F0..F7, SysEx): dropped with their data, running status cleared;
//   data bytes without status: ignored.
`default_nettype none

module midi_parser (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  in_data,
    input  wire        in_valid,
    output logic [7:0] ev_status,
    output logic [7:0] ev_d1,
    output logic [7:0] ev_d2,
    output logic       ev_valid
);

    logic [7:0] running;   // 0 = no running status
    logic [7:0] d1;
    logic       have_d1;
    logic       two_bytes;

    assign two_bytes = !(running[7:4] == 4'hC || running[7:4] == 4'hD);

    always_ff @(posedge clk) begin
        ev_valid <= 1'b0;
        if (rst) begin
            running   <= '0;
            d1        <= '0;
            have_d1   <= 1'b0;
            ev_status <= '0;
            ev_d1     <= '0;
            ev_d2     <= '0;
        end else if (in_valid) begin
            if (in_data >= 8'hF8) begin
                ev_status <= in_data;
                ev_d1     <= '0;
                ev_d2     <= '0;
                ev_valid  <= 1'b1;
            end else if (in_data >= 8'hF0) begin
                running <= '0;
                have_d1 <= 1'b0;
            end else if (in_data[7]) begin
                running <= in_data;
                have_d1 <= 1'b0;
            end else if (running != 8'h00) begin
                if (two_bytes && !have_d1) begin
                    d1      <= in_data;
                    have_d1 <= 1'b1;
                end else begin
                    have_d1  <= 1'b0;
                    ev_valid <= 1'b1;
                    ev_d1    <= two_bytes ? d1 : in_data;
                    if (!two_bytes) begin
                        ev_status <= running;
                        ev_d2     <= '0;
                    end else if (running[7:4] == 4'h9 && in_data == 8'h00) begin
                        ev_status <= {4'h8, running[3:0]};
                        ev_d2     <= 8'h40;
                    end else begin
                        ev_status <= running;
                        ev_d2     <= in_data;
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
