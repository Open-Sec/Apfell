from app import apfell, db_objects
from app.database_models.model import *
from sanic.response import raw, file
from sanic_jwt.decorators import protected, inject_user
from fpdf import FPDF, HTMLMixin
import base64
import json as js


# ------- REPORTING-BASED API FUNCTION -----------------
@apfell.route(apfell.config['API_BASE'] + "/reporting/full_timeline", methods=['GET', 'POST'])
@inject_user()
@protected()
async def reporting_full_timeline_api(request, user):
    # post takes in configuration parameters for how to display the timeline
    # {"output_type": {pdf | csv }, "cmd_output": {true | false}, "strict": {time | task}}
    #  strict refers to if we need to adhere to strict ordering of commands issued, response timings, or nothing
    if user['current_operation'] != "":
        operation = await db_objects.get(Operation, name=user['current_operation'])
        pdf = PDF()
        pdf.set_author(user['username'])
        pdf.set_title("Operation {}'s Full Timeline Report.pdf".format(user['current_operation']))
        # call to alias_nb_pages allows us refer to total page numbers with {nb} dynamically
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_font('Times', 'B', 20)
        pdf.set_fill_color(224, 224, 224)
        pdf.cell(w=36, h=pdf.font_size, txt="Timestamp", border=0, align="C", fill=True, ln=0)
        pdf.cell(w=35, h=pdf.font_size, txt="Host", border=0, align="C", fill=True, ln=0)
        pdf.cell(w=30, h=pdf.font_size, txt="User", border=0, align="C", fill=True, ln=0)
        pdf.cell(w=20, h=pdf.font_size, txt="PID", border=0, align="C", fill=True, ln=0)
        pdf.cell(w=0, h=pdf.font_size, txt="Task", border=0, align="C", fill=True, ln=1)
        pdf.set_font('Times', '', 10)
        pdf.set_fill_color(244, 244, 244)
        data = {}
        data['cmd_output'] = False
        data['strict'] = "task"
        if request.method == "POST":
            config = request.json
            if 'cmd_output' in config:
                data['cmd_output'] = config['cmd_output']
            if 'strict' in config:
                data['strict'] = config['strict']
        pdf = await get_all_data(operation, pdf, data)
        pdf.output("./app/files/{}/full_timeline.pdf".format(user['current_operation']), dest='F')
        #return await file("./app/files/{}/full_timeline.pdf".format(user['current_operation']))
        #final_pdf = pdf.output(dest='S').encode('latin-1')
        contents = open("./app/files/{}/full_timeline.pdf".format(user['current_operation']), 'rb').read()
        return raw(base64.b64encode(contents))

    else:
        return raw("Must select a current operation to generate a report")


async def get_all_data(operation, pdf, config):
    # need to get all callbacks, tasks, responses in a dict with the key being the timestamp
    all_data = {}
    callbacks = await db_objects.execute(Callback.select().where(Callback.operation == operation))
    height = pdf.font_size + 1
    for c in callbacks:
        all_data[c.init_callback] = {"callback": c}
        tasks = await db_objects.execute(Task.select().where(Task.callback == c))
        for t in tasks:
            all_data[t.timestamp] = {"task": t}
            if 'cmd_output' in config and config['cmd_output']:
                responses = await db_objects.execute(Response.select().where(Response.task == t))
                if 'strict' in config and config['strict'] == "time":
                    # this will get output as it happened, not grouped with the corresponding command
                    for r in responses:
                        all_data[r.timestamp] = {"response": r}
                elif 'strict' in config and config['strict'] == "task":
                    # this will group output with the corresponding task, like we see it in the operator view
                    response_data = {}
                    for r in responses:
                        response_data[r.timestamp] = {"response": r}
                    # now that it's all grouped together into a dictionary, associate it with the task
                    all_data[t.timestamp] = {"task": t, "response": response_data}
    highlight = False
    for key in sorted(all_data.keys()):
        if "callback" in all_data[key]:
            pdf.set_fill_color(255, 204, 204)
            c = all_data[key]['callback'].to_json()
            pdf.cell(w=36, h=height, txt=c['init_callback'], border=2, align="L", fill=True, ln=0)
            pdf.cell(w=35, h=height, txt=c['host'], border=2, align="C", fill=True, ln=0)
            pdf.cell(w=30, h=height, txt=c['user'], border=2, align="C", fill=True, ln=0)
            pdf.cell(w=20, h=height, txt=str(c['pid']), border=2, align="C", fill=True, ln=0)
            output = "New Callback of type " + all_data[key]['callback'].registered_payload.payload_type.ptype + \
                " with description: " + c['description']
            if len(output) > 45:
                pdf.cell(w=0, h=height, txt=output[0:45], border=0, align="L", fill=True, ln=1)
                # it's too long to fit on one line, start a new line for it and do a multi-cell
                pdf.multi_cell(w=0, h=height, txt=output[45:], border=0, align="L", fill=True)
            else:
                pdf.cell(w=0, h=height, txt=output, border=0, align="L", fill=highlight, ln=1)
        elif "task" in all_data[key]:
            pdf.set_fill_color(244, 244, 244)
            task = all_data[key]['task']
            task_json = task.to_json()
            callback = all_data[key]['task'].callback.to_json()
            pdf.cell(w=36, h=height, txt=task_json['timestamp'], border=0, align="L", fill=highlight, ln=0)
            pdf.cell(w=35, h=height, txt=callback['host'], border=0, align="C", fill=highlight, ln=0)
            pdf.cell(w=30, h=height, txt=callback['user'], border=0, align="C", fill=highlight, ln=0)
            pdf.cell(w=20, h=height, txt=str(callback['pid']), border=0, align="C", fill=highlight, ln=0)
            if task.command.cmd == "load":
                command = task.command.cmd + " " + js.loads(task_json['params'].replace("'", "\""))['cmd']
            else:
                command = task.command.cmd + " " + task_json['params']
            if len(command) > 45:
                pdf.cell(w=0, h=height, txt=command[0:45], border=0, align="L", fill=highlight, ln=1)
                # it's too long to fit on one line, start a new line for it and do a multi-cell
                pdf.multi_cell(w=0, h=pdf.font_size, txt=command[45:], border=0, align="L", fill=highlight)
            else:
                pdf.cell(w=0, h=height, txt=command, border=0, align="L", fill=highlight, ln=1)
            highlight = not highlight
            if 'cmd_output' in config and config['cmd_output']:
                if 'response' in all_data[key]:
                    # this means we're grouping all of the response output with the task
                    for r in sorted(all_data[key]['response'].keys()):
                        r_json = all_data[key]['response'][r]['response'].to_json()
                        pdf.set_fill_color(204, 229, 255)
                        pdf.cell(w=36, h=height, txt=r_json['timestamp'], border=0, align="L", fill=True, ln=0)
                        pdf.multi_cell(w=0, h=height, txt=r_json['response'], border=0, align="L", fill=True)
        elif "response" in all_data[key]:
            # this means we're doing true time, not grouping all responses with their tasks
            r_json = all_data[key]['response'].to_json()
            pdf.set_fill_color(204, 229, 255)
            pdf.cell(w=38, h=height, txt=r_json['timestamp'], border=0, align="L", fill=True, ln=0)
            pdf.multi_cell(w=0, h=height, txt=r_json['response'], border=0, align="L", fill=True)
    return pdf


class PDF(FPDF, HTMLMixin):
    def header(self):
        # Logo
        title = "Apfell - Timeline"
        # image location, top-left x, top-left y, width (height auto calculated to keep proportions)
        self.image('./app/static/apfell_cropped.png', 10, 8, 20)
        # Arial bold 15
        self.set_font('Arial', 'B', 15)
        # Calculate width of title and position
        w = self.get_string_width(title) + 6
        self.set_x((210 - w) / 2)
        # Colors of frame, background and text
        #self.set_draw_color(0, 80, 180)
        #self.set_fill_color(230, 230, 0)
        #self.set_text_color(220, 50, 50)
        # Thickness of frame (1 mm)
        self.set_line_width(1)
        # Title
        # last 1 here means that the cell must be filled
        self.cell(w, 9, title, 1, 1, 'C', 0)
        # put some line breaks between here and where the rest of the body starts
        self.ln(10)

    # Page footer
    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        # Arial italic 8
        self.set_font('Arial', 'I', 8)
        # Page number
        self.cell(0, 10, 'Page ' + str(self.page_no()) + '/{nb}', 0, 0, 'C')

