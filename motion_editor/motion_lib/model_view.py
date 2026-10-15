"""On-demand software 3D view, adapted from gui_full. No serial access."""
import math
from .axis_signs import DISPLAY_SIGNS
from PyQt5.QtCore import QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget

ROBI_REFERENCE_POSES = {'立ちポーズ正面~~': {2: 2.5, 3: 12.0, 4: -30.0, 5: 11.5, 6: -2.0, 7: -1.5, 8: -12.0, 9: 26.0, 10: -14.5, 11: 3.5, 12: 2.0, 13: 2.0, 14: 7.5, 15: -8.5, 16: -3.0, 17: 61.0, 18: 43.5, 19: 5.0, 20: -59.0, 21: -41.5}, '座りポーズ正面~~~': {2: -0.5, 3: -95.0, 4: -30.0, 5: -15.5, 6: -2.0, 7: 1.5, 8: 95.0, 9: 26.0, 10: 12.5, 11: 3.5, 12: 2.0, 13: 2.0, 14: 7.5, 15: -8.5, 16: -15.0, 17: 76.0, 18: 2.5, 19: 17.0, 20: -74.0, 21: -0.5}, 'クレードルポーズ正面~~~': {2: 0.0, 3: -83.0, 4: -15.0, 5: -4.5, 6: -3.5, 7: 1.0, 8: 83.0, 9: 11.0, 10: 1.5, 11: 2.0, 12: 2.0, 13: 2.0, 14: 7.5, 15: -8.5, 16: -3.0, 17: 61.0, 18: 43.5, 19: 5.0, 20: -59.0, 21: -41.5}}

def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def rotation(axis, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    if axis == 'x':
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if axis == 'y':
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

def advance(point, frame, offset):
    return tuple(point[i] + sum(frame[i][j] * offset[j] for j in range(3)) for i in range(3))

class PoseView(QWidget):
    selected = pyqtSignal(int)

    def __init__(self, controls):
        super().__init__()
        self.controls = {c.id: c for c in controls}
        self.active = 16
        self.yaw = 30
        self.pitch = 12
        self.hits = []
        self.drag_origin = None
        self.zero = dict(ROBI_REFERENCE_POSES['立ちポーズ正面~~'])
        self._scene_key = None
        self._scene_cache = None
        self._projected_key = None
        self._projected_faces = []
        self._camera_key = None
        self._camera_frame = None
        self.setMinimumSize(450, 430)

    def scene(self):
        # x: robot left, y: up, z: forward. Dimensions are illustrative.
        # Movement roles: https://arutora.com/4105 and /4189.
        # Signs below are a display convention, NOT verified servo polarity.
        angles = {i: (c.angle.value() - self.zero[i])
                  for i, c in self.controls.items()}
        key = tuple(angles.items())
        if key == self._scene_key:
            return self._scene_cache
        faces, joints = [], []

        def box(center, frame, size, color):
            vertices = [advance(center, frame, (x * size[0]/2, y * size[1]/2, z * size[2]/2))
                        for x, y, z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                        (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
            for indices, shade in [((0,1,2,3),.60),((4,5,6,7),1.0),((0,4,7,3),.75),
                                   ((1,5,6,2),.85),((3,2,6,7),1.15),((0,1,5,4),.55)]:
                # Subdivide surfaces to keep small facial details visible in depth sorting.
                corners = [vertices[i] for i in indices]
                def surface(u,v):
                    return tuple((1-u)*(1-v)*corners[0][k] + u*(1-v)*corners[1][k]
                                 + u*v*corners[2][k] + (1-u)*v*corners[3][k] for k in range(3))
                # Keep large shells subdivided so their rear faces do not hide details.
                steps = 6 if size[0] >= .5 else 1
                for row in range(steps):
                    for col in range(steps):
                        u,v = row/steps,col/steps
                        faces.append(([surface(u,v),surface(u+1/steps,v),
                                       surface(u+1/steps,v+1/steps),surface(u,v+1/steps)],
                                      QColor(color).lighter(int(shade*100))))

        def ellipsoid(center, frame, size, color, rings=6, segments=12):
            # Transform each shared vertex once rather than once per adjacent face.
            vertices = []
            for row in range(rings+1):
                latitude = -math.pi/2 + math.pi*row/rings
                cos_lat, sin_lat = math.cos(latitude), math.sin(latitude)
                vertices.append([advance(center,frame,
                    (size[0]/2*cos_lat*math.cos(2*math.pi*col/segments),
                     size[1]/2*sin_lat,
                     size[2]/2*cos_lat*math.sin(2*math.pi*col/segments)))
                    for col in range(segments)])
            for row in range(rings):
                shade = .75 + .25*math.sin(math.pi*(row+.5)/rings)
                shaded = QColor(color).lighter(int(shade*100))
                for col in range(segments):
                    nxt=(col+1)%segments
                    faces.append(([vertices[row][col],vertices[row][nxt],
                                   vertices[row+1][nxt],vertices[row+1][col]],shaded))

        def joint(i, point, frame, axis):
            joints.append((i, point, frame, axis))
            return matmul(frame, rotation(axis, DISPLAY_SIGNS[i] * angles[i]))

        base = (0, -.65, 0)
        torso = joint(12, base, rotation('y', 0), 'y')
        ellipsoid(base, rotation('y',0), (.80,.25,.58), '#36383b')
        chest = advance(base, torso, (0,.57,0))
        ellipsoid(chest, torso, (.88,1.05,.62), '#eeeae1')
        ellipsoid(advance(chest,torso,(0,.12,.30)),torso,(.38,.26,.08),'#b33d35')
        neck = advance(base, torso, (0,1.16,0))
        nf = joint(13, neck, torso, 'y')
        neck2 = advance(neck, nf, (0,.09,0))
        nf = joint(14, neck2, nf, 'z')
        neck3 = advance(neck2, nf, (0,.09,0))
        nf = joint(15, neck3, nf, 'x')
        head = advance(neck3, nf, (0,.34,0))
        ellipsoid(head,nf,(1.02,.85,.78),'#e9e6dd')
        ellipsoid(advance(head,nf,(0,0,.31)),nf,(.85,.56,.25),'#363533')
        for x in [-.20,.20]:
            ellipsoid(advance(head,nf,(x,.02,.43)),nf,(.25,.29,.09),'#edece0')
            ellipsoid(advance(head,nf,(x,.02,.48)),nf,(.19,.23,.07),'#242f31')
            ellipsoid(advance(head,nf,(x-.035,.06,.52)),nf,(.055,.065,.025),'#92c6bf')
        ellipsoid(advance(head,nf,(0,-.22,.42)),nf,(.18,.055,.06),'#b26c58')
        ellipsoid(neck,torso,(.48,.16,.48),'#77b9d3')
        for sign, arm, color in [(-1,16,'#454647'),(1,19,'#454647')]:
            shoulder = advance(base, torso, (sign*.63,1.0,0))
            frame = joint(arm, shoulder, torso, 'x')
            ellipsoid(shoulder,frame,(.32,.32,.39),color)
            roll = advance(shoulder,frame,(sign*.13,0,0))
            frame = joint(arm+1,roll,frame,'z')
            # The Heart standing reference defines the model rest pose, arms down.
            ellipsoid(advance(roll,frame,(0,-.30,0)),frame,(.29,.60,.33),color)
            elbow = advance(roll,frame,(0,-.62,0))
            frame = joint(arm+2,elbow,frame,'x')
            ellipsoid(elbow,frame,(.29,.22,.32),'#292b2d')
            ellipsoid(advance(elbow,frame,(0,-.29,0)),frame,(.33,.52,.37),color)
            ellipsoid(advance(elbow,frame,(0,-.58,.03)),frame,(.38,.26,.40),'#e9e6dd')
        for sign, leg, color in [(-1,2,'#434547'),(1,7,'#434547')]:
            hip = advance(base, rotation('y',0), (sign*.25,-.10,0))
            frame = joint(leg,hip,rotation('y',0),'z')
            frame = joint(leg+1,hip,frame,'x')
            ellipsoid(advance(hip,frame,(0,-.32,0)),frame,(.34,.67,.39),color)
            knee = advance(hip,frame,(0,-.66,0))
            frame = joint(leg+2,knee,frame,'x')
            ellipsoid(knee,frame,(.35,.24,.39),'#292b2d')
            ellipsoid(advance(knee,frame,(0,-.32,0)),frame,(.37,.62,.42),'#e9e6dd')
            ankle = advance(knee,frame,(0,-.65,0))
            frame = joint(leg+3,ankle,frame,'x')
            frame = joint(leg+4,ankle,frame,'z')
            ellipsoid(advance(ankle,frame,(0,-.15,.15)),frame,(.45,.29,.76),'#e9e6dd')
            ellipsoid(advance(ankle,frame,(0,-.26,.15)),frame,(.46,.10,.77),'#713d36')
        self._scene_key = key
        self._scene_cache = (faces, joints)
        return self._scene_cache

    def camera(self, point):
        key = (self.pitch, self.yaw)
        if key != self._camera_key:
            self._camera_frame = matmul(rotation('x', self.pitch), rotation('y', self.yaw))
            self._camera_key = key
        x,y,z = point[0],point[1]+.35,point[2]
        return tuple(row[0]*x + row[1]*y + row[2]*z for row in self._camera_frame)

    def project(self, point):
        x,y,z = self.camera(point)
        scale = min(self.width()/4.8,self.height()/5.2) * 6 / (6-z)
        return QPointF(self.width()/2+x*scale,self.height()/2-y*scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#17212e'))
        painter.setPen(QPen(QColor('#304154'),1))
        for n in range(-4,5):
            v=n*.4
            painter.drawLine(self.project((v,-2.50,-1.6)),self.project((v,-2.50,1.6)))
            painter.drawLine(self.project((-1.6,-2.50,v)),self.project((1.6,-2.50,v)))
        faces,joints = self.scene()
        # Cache projection and depth order until geometry, camera, or size changes.
        projected_key=(self._scene_key,self.yaw,self.pitch,self.width(),self.height())
        if projected_key != self._projected_key:
            projected={}
            def project_once(vertex):
                if vertex not in projected:
                    x,y,z=self.camera(vertex)
                    scale=min(self.width()/4.8,self.height()/5.2)*6/(6-z)
                    projected[vertex]=(QPointF(self.width()/2+x*scale,self.height()/2-y*scale),z)
                return projected[vertex]
            polygons=[]
            for vertices,color in faces:
                points=[project_once(vertex) for vertex in vertices]
                polygons.append((sum(z for _,z in points)/len(points),
                                 QPolygonF([point for point,_ in points]),color))
            self._projected_faces=sorted(polygons,key=lambda face:face[0])
            self._projected_key=projected_key
        for _,polygon,color in self._projected_faces:
            painter.setBrush(color)
            painter.setPen(QPen(color,.6))
            painter.drawPolygon(polygon)
        self.hits=[]
        for i,point,frame,axis in joints:
            anchor=self.project(point)
            screen=QPointF(anchor)
            # Separate screen-space handles without moving the real rotation pivots.
            for step in range(161):
                if all(math.hypot(screen.x()-p.x(),screen.y()-p.y()) >= 32
                       for _,p in self.hits):
                    break
                radius=24+12*(step//8)
                theta=2*math.pi*(step%8)/8
                screen=anchor+QPointF(radius*math.cos(theta),radius*math.sin(theta))
            self.hits.append((i,screen))
            if screen != anchor:
                painter.setPen(QPen(QColor('#91a0b3'),1))
                painter.drawLine(anchor,screen)
            if i != self.active and (i in (5,6,10,11) or screen != anchor):
                painter.setPen(QColor('#d1d9e6'))
                painter.drawText(screen+QPointF(9,4),f'ID{i}')
            painter.setBrush(QColor('#ffed82' if i==self.active else '#17212e'))
            painter.setPen(QPen(QColor('#ffed82' if i==self.active else '#ffffff'),2))
            painter.drawEllipse(screen,6,6)
            if i==self.active:
                vector={'x':(.35,0,0),'y':(0,.35,0),'z':(0,0,.35)}[axis]
                painter.drawLine(self.project(advance(point,frame,tuple(-v for v in vector))),
                                 self.project(advance(point,frame,vector)))
                painter.drawText(screen+QPointF(10,-12),f'ID{i}')
        painter.setPen(QColor('#f3a35a'))
        painter.drawText(16,25,'● 右側 / ROBOT RIGHT')
        painter.setPen(QColor('#52bfe8'))
        painter.drawText(16,47,'● 左側 / ROBOT LEFT')
        painter.setPen(QColor('#d1d9e6'))
        painter.drawText(16,self.height()-15,'関節: 上下ドラッグ  |  空白: 視点回転  |  黄色の線: 選択関節の回転軸')
        origin=(1.25,-.75,0)
        for delta,label,color in [((.45,0,0),'左','#52bfe8'),((0,.45,0),'上','#8ad4ac'),((0,0,.65),'前','#f3a35a')]:
            end=tuple(origin[i]+delta[i] for i in range(3))
            painter.setPen(QPen(QColor(color),2))
            painter.drawLine(self.project(origin),self.project(end))
            painter.drawText(self.project(end)+QPointF(4,0),label)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        nearby = [(math.hypot(p.x() - event.x(), p.y() - event.y()), i) for i, p in self.hits]
        distance, servo_id = min(nearby, default=(999, 0))
        self.drag_joint = servo_id if distance < 18 else None
        if self.drag_joint is not None:
            self.active = servo_id
            self.selected.emit(servo_id)
        self.drag_origin = event.pos()
        self.update()

    def mouseMoveEvent(self, event):
        if self.drag_origin is None:
            return
        delta = event.pos() - self.drag_origin
        if self.drag_joint is not None:
            control = self.controls[self.drag_joint]
            lo, hi = control.min_angle.value(), control.max_angle.value()
            if lo <= hi:
                control.angle.setValue(max(lo, min(hi, control.angle.value() - delta.y() * .5)))
        else:
            self.yaw += delta.x() * .5
            self.pitch = max(-85, min(85, self.pitch + delta.y() * .5))
        self.drag_origin = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_origin = None
