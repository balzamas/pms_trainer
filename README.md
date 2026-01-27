# PMS trainer
Property manager system trainer

Generates random scenarios to train your staff. Focus is solely on creating new bookings/changing existing bookings.

Creates log files for controlling in the folder /tasks/.

![Screenshot UI.](sshot.png)

## Run under Linux
Needs python3-tk (Install in Debian systems: `sudo apt install -y python3 python3-tk`)

run: `python3 main.py`

## Run under Windows
Run main.exe

## config.json
### "guests"
Example guests - should exist in your PMS as well.

### "room_categories"
Your room categories with your max/min number of guests in the room.

### "extra_services"
Your extra services.

### "follow_up_tasks"
After a reservation is created, a follow up task can appear. The reservation has to be changed.

### "breakfast_types"/"breakfast_policy"
If you have breakfast on order, you can set here your options. If you don't have this, set "enabled": false.

### "booking_window"
Earliest/latest date for the generated scenarios. In case you don't have a training system.

--------------------------------------------

Coded by ChatGPT, prompted by d.berger@dontsniff.co.uk

Repo: https://github.com/balzamas/pms_trainer/
